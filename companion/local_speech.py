"""User-local Windows speech, with engine word-boundary timestamps."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import threading
import wave


def boundaries(text, marks, duration):
    """Commit a word only after the next word starts; never interpolate chars.

    Windows indices count UTF-16 units, Python counts Unicode code points.
    Duplicate positions (e.g. spoken numbers) remain one complete text unit.
    """
    encoded = text.encode('utf-16-le')
    valid = []
    for m in marks:
        pos, count, seconds = m.get('position'), m.get('count'), m.get('seconds')
        if not isinstance(pos, int) or not isinstance(count, int) or pos < 0 or count <= 0:
            continue
        if not isinstance(seconds, (float, int)) or not 0 <= seconds <= duration:
            continue
        piece = encoded[pos*2:(pos+count)*2].decode('utf-16-le', errors='ignore')
        if piece != m.get('text'):
            # Engines with SSML-relative indices cannot safely commit partial text.
            return []
        charpos = len(encoded[:pos*2].decode('utf-16-le', errors='ignore'))
        if valid and (charpos < valid[-1][0] or seconds < valid[-1][1]):
            return []
        valid.append((charpos, float(seconds)))
    result = []
    for index, (pos, seconds) in enumerate(valid):
        if index and pos > valid[index-1][0]:
            result.append({'end': pos, 'seconds': seconds})
    if valid:
        result.append({'end': len(text), 'seconds': duration})
    return result


class LocalSpeech:
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        self.closed = False

    def _request(self, request):
        if os.name != 'nt':
            raise RuntimeError('本地语音目前仅支持 Windows')
        with self.lock:
            if self.closed:
                raise RuntimeError('本地语音已关闭')
            if not self.proc or self.proc.poll() is not None:
                self.proc = subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                    str(Path(__file__).with_name('local_speech.ps1'))], stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            proc = self.proc
            if self.closed:
                proc.terminate()
                raise RuntimeError('本地语音已关闭')
            # A hung SAPI worker must not retain a thread/lock forever.
            timer = threading.Timer(20, lambda: proc.kill() if proc.poll() is None else None)
            timer.daemon = True
            timer.start()
            try:
                proc.stdin.write(json.dumps(request, ensure_ascii=False)+'\n')
                proc.stdin.flush()
                line=proc.stdout.readline()
            finally:
                timer.cancel()
            if not line:
                raise RuntimeError('本地语音引擎退出，请切换音色重试')
            result=json.loads(line)
            if result.get('error'):
                raise RuntimeError(result['error'])
            return result

    async def voices(self):
        return (await asyncio.to_thread(self._request, {'list':True}))['voices']

    async def speech(self, text, voice):
        result=await asyncio.to_thread(self._request, {'text':text,'voice':voice})
        pcm=base64.b64decode(result['audio'])
        duration=len(pcm)/(result['sample_rate']*2)
        output=io.BytesIO()
        with wave.open(output,'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(result['sample_rate']); wav.writeframes(pcm)
        return output.getvalue(), duration, boundaries(text,result['marks'],duration)

    async def close(self):
        self.closed = True
        proc=self.proc
        if proc and proc.poll() is None:
            proc.terminate()
        await asyncio.to_thread(self._close_locked)

    def _close_locked(self):
        with self.lock:
            proc = self.proc
            if proc:
                if proc.poll() is None:
                    proc.terminate()
                proc.wait(timeout=5)
            self.proc = None

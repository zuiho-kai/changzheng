"""Measure real first PCM/body bytes separately from complete speech latency."""
import asyncio
import io
import json
from pathlib import Path
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from companion.providers import Provider, BASE, speech_request

OUTPUT = ROOT / 'artifacts/voice-review'
TEXTS = {
    'short': '等一下，说谁呆呢？',
    'reply': '等一下，说谁呆呢？我刚才那叫深思熟虑。好吧，其实在发呆。',
}

async def measure(provider, text, stream, response_format):
    start = time.perf_counter()
    row = {'stream': stream, 'format': response_format, 'text': text}
    data = bytearray()
    async with provider.client.stream('POST', BASE + '/audio/speech', headers=provider.headers(),
            json=speech_request(text, 'diana', 'playful', stream=stream, response_format=response_format)) as response:
        await provider.check(response)
        row['headers_ms'] = round((time.perf_counter()-start)*1000)
        chunks = 0
        async for chunk in response.aiter_bytes():
            if not chunk:
                continue
            chunks += 1
            now = round((time.perf_counter()-start)*1000)
            row.setdefault('first_body_ms', now)
            data.extend(chunk)
            # PCM has no container bytes. WAV data is located rather than assuming 44 bytes.
            pcm_offset = 0 if response_format == 'pcm' else data.find(b'data') + 8
            if response_format == 'pcm' or (pcm_offset >= 8 and len(data) > pcm_offset):
                row.setdefault('first_audio_ms', now)
                if len(data) - pcm_offset >= 4800:
                    row.setdefault('first_100ms_audio_ms', now)
        row.update(total_ms=round((time.perf_counter()-start)*1000), bytes=len(data), chunks=chunks)
    if response_format == 'wav':
        with wave.open(io.BytesIO(data), 'rb') as wav:
            rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
            pcm = wav.readframes(wav.getnframes())
    else:
        rate, channels, width, pcm = 24000, 1, 2, data
    row['duration'] = round(len(pcm)/(rate*channels*width), 3)
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return row, out.getvalue()

async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = []
    provider = Provider()
    try:
        for trial in range(2):
            for label, text in TEXTS.items():
                for stream, fmt in [(False, 'wav'), (True, 'wav'), (True, 'pcm')]:
                    row = {'trial': trial+1, 'length': label, 'stream': stream, 'format': fmt}
                    try:
                        async with asyncio.timeout(25):
                            result, audio = await measure(provider, text, stream, fmt)
                        row.update(result)
                        name = f'latency-{label}-{stream}-{fmt}-{trial+1}.wav'
                        (OUTPUT/name).write_bytes(audio)
                        row['file'] = name
                    except Exception as exc:
                        row['error'] = type(exc).__name__ + ': ' + str(exc)[:160]
                    rows.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        await provider.close()
        (OUTPUT/'audio-latency.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf8')

if __name__ == '__main__':
    asyncio.run(main())

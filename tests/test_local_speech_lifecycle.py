import asyncio
import threading
from companion.local_speech import LocalSpeech


def test_cancelled_queued_thread_cannot_restart_worker_after_close(monkeypatch):
    async def run():
        created = []
        reading = threading.Event()
        class Pipe:
            def write(self, data): pass
            def flush(self): pass
        class Process:
            def __init__(self, *args, **kwargs):
                self.stdin = Pipe()
                self.stdout = self
                self.done = threading.Event()
                created.append(self)
            def readline(self):
                reading.set()
                self.done.wait(3)
                return ''
            def poll(self): return 0 if self.done.is_set() else None
            def terminate(self): self.done.set()
            def kill(self): self.done.set()
            def wait(self, timeout=None):
                assert self.done.wait(timeout)
                return 0
        monkeypatch.setattr('companion.local_speech.subprocess.Popen', Process)
        speech = LocalSpeech()
        first = asyncio.create_task(speech.voices())
        await asyncio.to_thread(reading.wait, 1)
        second = asyncio.create_task(speech.voices())
        await asyncio.sleep(.05)
        first.cancel()
        second.cancel()
        await asyncio.gather(first, second, return_exceptions=True)
        await speech.close()
        assert len(created) == 1
        assert all(p.poll() is not None for p in created)
        assert speech.proc is None
    asyncio.run(run())

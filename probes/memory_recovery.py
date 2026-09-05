"""Kill an isolated server during extraction; restart and verify real recall."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import time
import httpx
import websockets
from companion.secrets import get_key

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:17866'


async def main():
    folder = ROOT / 'artifacts' / ('runtime-memory-' + str(int(time.time())))
    folder.mkdir()
    env = {**os.environ, 'SILICONFLOW_API_KEY': get_key(), 'CHANGZHENG_DATA_DIR': str(folder)}
    report = {'checks': {}}
    proc = None
    log = (folder / 'server.log').open('w', encoding='utf-8')
    def launch():
        return subprocess.Popen([str(ROOT / '.venv/Scripts/python.exe'), '-m', 'uvicorn',
            'companion.app:app', '--host', '127.0.0.1', '--port', '17866', '--log-level', 'warning'],
            cwd=ROOT, env=env, stdout=log, stderr=log,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    def kill():
        if proc and proc.poll() is None:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            proc.wait(10)
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as client:
        async def ready():
            for _ in range(100):
                try:
                    if (await client.get('/api/health')).is_success:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.1)
            raise AssertionError('isolated server did not start')
        try:
            proc = launch()
            await ready()
            await client.post('/api/settings', json={'audio_enabled': False, 'auto_memory': True})
            async with websockets.connect(BASE.replace('http:', 'ws:') + '/ws') as ws:
                await ws.recv()
                await ws.send(json.dumps({'type': 'message', 'voice': False,
                    'text': '请记住，我工作犯困时固定喝无糖绿茶，不喝含糖饮料。'}))
                for _ in range(500):
                    jobs = (await client.get('/api/memory-jobs')).json()
                    if jobs and jobs[0]['status'] == 'processing':
                        break
                    await asyncio.sleep(.01)
                else:
                    raise AssertionError('did not catch extraction in flight')
                report['checks']['killed_during_extraction'] = jobs[0]['status'] == 'processing'
                kill()
            proc = launch()
            await ready()
            for _ in range(300):
                jobs = (await client.get('/api/memory-jobs')).json()
                if jobs and jobs[0]['status'] == 'done':
                    break
                await asyncio.sleep(.2)
            report['checks']['job_recovered_without_resending'] = jobs[0]['status'] == 'done' and jobs[0]['attempts'] >= 2
            memories = (await client.get('/api/memories')).json()
            report['checks']['real_extraction_saved'] = any('绿茶' in m['content'] for m in memories)
            recalled = (await client.get('/api/recall', params={'q': '干活困了喝点什么', 'scene': 'work'})).json()
            report['checks']['paraphrase_recall_after_restart'] = any('绿茶' in m['content'] for m in recalled)
            for memory in memories:
                (await client.delete('/api/memories/' + memory['id'])).raise_for_status()
            kill()
            proc = launch()
            await ready()
            await asyncio.sleep(1)
            report['checks']['forget_survives_second_restart'] = (await client.get('/api/memories')).json() == []
            report['jobs'] = (await client.get('/api/memory-jobs')).json()
        finally:
            kill()
            log.close()
    (ROOT / 'artifacts/memory-recovery-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert all(report['checks'].values())


if __name__ == '__main__':
    asyncio.run(main())

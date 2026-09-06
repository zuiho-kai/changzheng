"""Real public Bilibili chat -> isolated companion -> actual SAPI playback/Live2D.

Read-only on Bilibili. Does not send chat or start a broadcast.
Run with the Python environment containing Playwright; app/receiver use .venv.
"""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import time

import httpx
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / '.venv/Scripts/python.exe')
BASE = 'http://127.0.0.1:17872'


async def main(room):
    folder = ROOT / 'artifacts' / f'runtime-bilibili-e2e-{int(time.time())}'
    folder.mkdir(parents=True)
    report = {'room': room, 'checks': {}, 'errors': []}
    receiver = None
    with (folder/'server.log').open('w') as log, (folder/'receiver.log').open('w') as relay_log:
        # preview script creates isolated data for this port, selects local SAPI,
        # and retrieves the existing DPAPI credential without printing it.
        server = subprocess.Popen([PYTHON, 'probes/live2d_preview.py', '--port', '17872',
                                   '--avatar', 'changzheng', '--data-dir', str(folder/'app-data')], cwd=ROOT, stdout=log, stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            async with httpx.AsyncClient(base_url=BASE, trust_env=False, timeout=10) as http:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError('Isolated server could not start (check port 17872)')
                    try:
                        if (await http.get('/api/health')).is_success:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(.1)
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(args=['--use-angle=swiftshader',
                        '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required'])
                    control = await browser.new_page(viewport={'width':1180,'height':850})
                    control.on('pageerror', lambda e: report['errors'].append(str(e)))
                    await control.goto(BASE)
                    await control.wait_for_function("document.querySelector('#connection').textContent==='已连接'")
                    await control.locator('[data-scene=live]').click()
                    stage = await browser.new_page(viewport={'width':1280,'height':720})
                    await stage.goto(BASE+'/stage')
                    model = stage.frame_locator('#avatar').frame_locator('#live2d-frame').locator('body')
                    await stage.frame_locator('#avatar').frame_locator('#live2d-frame').locator('body[data-ready=true]').wait_for(timeout=60000)
                    await model.evaluate("el=>{window.maxLiveMouth=0;window.mouthProbe=setInterval(()=>{window.maxLiveMouth=Math.max(window.maxLiveMouth,Number(el.dataset.mouth)||0)},20)}")
                    receiver = subprocess.Popen([PYTHON, '-m', 'companion.bilibili', '--room', str(room),
                        '--target', BASE, '--seconds', '75', '--report', str(folder/'receiver.json')],
                        cwd=ROOT, stdout=relay_log, stderr=relay_log, creationflags=subprocess.CREATE_NO_WINDOW)
                    await stage.wait_for_function("document.querySelector('#caption').textContent.length>1", timeout=90000)
                    report['heard_caption'] = await stage.locator('#caption').inner_text()
                    report['max_mouth'] = await model.evaluate('()=>window.maxLiveMouth')
                    state = (await http.get('/api/state')).json()
                    live_inputs = [m['content'] for m in state['history'] if m['role']=='user' and m.get('source')=='live']
                    report['live_inputs'] = live_inputs
                    report['receiver'] = json.loads((folder/'receiver.json').read_text(encoding='utf8'))
                    report['checks'] = {
                        'real_bilibili_event_received': report['receiver']['received'] > 0,
                        'forwarded_to_local_inbox': report['receiver']['forwarded'] > 0,
                        'live_source_in_history': bool(live_inputs),
                        'played_public_caption': bool(report['heard_caption']),
                        'audio_drives_live2d': report['max_mouth'] > .1,
                    }
                    if receiver.poll() is None:
                        receiver.terminate(); receiver.wait(timeout=10)
                    await stage.screenshot(path=str(ROOT/'artifacts/bilibili-live-speaking.png'))
                    # Let the real utterance finish; a two-character prefix only
                    # proves playback started, not that an answer completed.
                    for _ in range(200):
                        state = (await http.get('/api/state')).json()
                        if state['status'] == 'idle' and not state['turn_id']:
                            break
                        await asyncio.sleep(.2)
                    report['played_answers'] = [m['content'] for m in state['history'] if m['role']=='assistant']
                    report['checks']['answer_completed'] = bool(report['played_answers']) and not state['turn_id']
                    await control.locator('#stop-button').click()
                    await stage.frame_locator('#avatar').frame_locator('#live2d-frame').locator('body[data-mouth="0"]').wait_for(timeout=10000)
                    report['checks']['mouth_closed_at_end'] = True
                    await browser.close()
        except Exception as error:
            report['errors'].append(type(error).__name__ + ': ' + str(error))
        finally:
            for process in (receiver, server):
                if process and process.poll() is None:
                    process.terminate(); process.wait(timeout=10)
    (ROOT/'artifacts/bilibili-live-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))
    assert report['checks'] and all(report['checks'].values()) and not report['errors']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--room', type=int, required=True)
    asyncio.run(main(parser.parse_args().room))

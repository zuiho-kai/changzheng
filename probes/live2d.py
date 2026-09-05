"""Real local model + TTS acceptance, owns an isolated server and browser."""
import asyncio
import json
import io
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
from playwright.async_api import async_playwright
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from companion.secrets import get_key

BASE = 'http://127.0.0.1:17867'


async def main():
    folder = ROOT / 'artifacts' / ('runtime-live2d-' + str(int(time.time())))
    folder.mkdir(parents=True)
    env = {**os.environ, 'CHANGZHENG_DATA_DIR':str(folder), 'CHANGZHENG_AUDIT':'1', 'SILICONFLOW_API_KEY':get_key()}
    report = {'checks':{}}
    with (folder / 'server.log').open('w') as log:
        proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'companion.app:app', '--host','127.0.0.1','--port','17867','--no-access-log'], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
                for _ in range(100):
                    try:
                        if (await client.get('/api/health')).is_success: break
                    except httpx.HTTPError: pass
                    await asyncio.sleep(.1)
                await client.post('/api/settings', json={'voice':'local:Microsoft Huihui Desktop','auto_memory':False})
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
                    page = await browser.new_page(viewport={'width':1180,'height':850})
                    errors=[]
                    page.on('pageerror', lambda e:errors.append(str(e)))
                    await page.goto(BASE)
                    await page.wait_for_function("document.querySelector('#connection').textContent==='已连接'")
                    await page.locator('#avatar-preset').select_option('hiyori')
                    await page.frame_locator('#live2d-frame').locator('body[data-ready=true]').wait_for(timeout=30000)
                    report['checks']['real_model_rendered'] = True
                    await page.screenshot(path=str(ROOT/'artifacts/live2d-desktop-optimized.png'))
                    await page.set_viewport_size({'width':310,'height':390})
                    await page.evaluate("document.body.classList.add('compact')")
                    compact_png=await page.screenshot(path=str(ROOT/'artifacts/live2d-compact.png'))
                    crop=Image.open(io.BytesIO(compact_png)).convert('RGB').crop((55,50,255,280))
                    report['checks']['compact_resize_repaints_character']=sum(max(pixel)<150 for pixel in crop.getdata())>300
                    await page.evaluate("document.body.classList.remove('compact')")
                    await page.set_viewport_size({'width':1180,'height':850})
                    stage = await browser.new_page(viewport={'width':1920,'height':1080})
                    await stage.goto(BASE+'/stage')
                    overlay = stage.frame_locator('iframe')
                    live_model = overlay.frame_locator('#live2d-frame')
                    await live_model.locator('body[data-ready=true]').wait_for(timeout=30000)
                    await page.locator('#message').fill('请原样念出：今天我们在本机测试语音和角色动画。等我打断以后，没说完的内容就不要再接着说了。')
                    await page.locator('#chat-form .send-button').click()
                    await page.frame_locator('#live2d-frame').locator('body').evaluate("el=>new Promise((resolve,reject)=>{const start=performance.now();const timer=setInterval(()=>{if(Number(el.dataset.mouth)>.1){clearInterval(timer);resolve(true)}else if(performance.now()-start>30000){clearInterval(timer);reject(Error('no mouth movement'))}},30)})")
                    private_mouth = await live_model.locator('body').get_attribute('data-mouth')
                    report['checks']['private_speech_not_forwarded'] = float(private_mouth or 0)==0
                    await page.locator('#stop-button').click()
                    await page.frame_locator('#live2d-frame').locator('body[data-mouth="0"]').wait_for()
                    await page.locator('[data-scene=live]').click()
                    await page.locator('#message').fill('请原样念出：大家好，这里是小征的本地直播画面测试。我们正在测试嘴型同步，以及打断时立刻停止说话。')
                    await page.locator('#chat-form .send-button').click()
                    for _ in range(400):
                        value=float(await live_model.locator('body').get_attribute('data-mouth') or 0)
                        if value>.1: break
                        await asyncio.sleep(.05)
                    report['checks']['live_audio_drives_observer_mouth'] = value>.1
                    # Reconnect during a real ongoing utterance, not a new turn.
                    snapshots=[]
                    def received(payload):
                        data=json.loads(payload)
                        if data.get('type')=='state': snapshots.append(data)
                    stage.on('websocket',lambda socket:socket.on('framereceived',received))
                    await stage.reload()
                    await live_model.locator('body[data-ready=true]').wait_for(timeout=30000)
                    for _ in range(100):
                        value=float(await live_model.locator('body').get_attribute('data-mouth') or 0)
                        if value>.1: break
                        await asyncio.sleep(.03)
                    report['checks']['mid_turn_reload_recovers_mouth']=value>.1
                    report['checks']['reconnect_snapshot_has_current_turn']=bool(snapshots and snapshots[-1].get('turn_id'))
                    report['checks']['snapshot_excludes_private_data']=bool(snapshots and not ({'history','memories','tasks','key_configured','pending'} & snapshots[-1].keys()))
                    await stage.screenshot(path=str(ROOT/'artifacts/live2d-stage-optimized.png'))
                    start=time.monotonic()
                    await page.locator('#stop-button').click()
                    await live_model.locator('body[data-mouth="0"]').wait_for()
                    report['stop_to_closed_mouth_ms']=round((time.monotonic()-start)*1000)
                    report['checks']['stop_closes_mouth']=report['stop_to_closed_mouth_ms']<400
                    audit=(await client.get('/api/context')).json()
                    report['checks']['stop_discards_pending_audio']=audit['pending_count']==0
                    for _ in range(100):
                        state=(await client.get('/api/state')).json()
                        if state['status']=='idle': break
                        await asyncio.sleep(.03)
                    heard=[m['content'] for m in state['history'] if m['role']=='assistant']
                    report['checks']['interrupted_caption_is_played_prefix']=(await overlay.locator('#speech-bubble').text_content())==(heard[-1] if heard else '')
                    await page.locator('#message').fill('只回答一个字：好')
                    await page.locator('#chat-form .send-button').click()
                    for _ in range(300):
                        audit=(await client.get('/api/context')).json()
                        if audit['messages'] and audit['messages'][-1].get('content')=='只回答一个字：好': break
                        await asyncio.sleep(.03)
                    report['checks']['next_model_context_matches_played_history']=[m['content'] for m in audit['messages'] if m['role']=='assistant']==heard
                    await page.locator('#stop-button').click()
                    report['checks']['no_browser_errors']=not errors
                    report['errors']=errors
                    await page.locator('#avatar-preset').select_option('cat')
                    await overlay.locator('.cat-svg:not([hidden])').wait_for()
                    report['checks']['preset_switch_reaches_observer']=await overlay.locator('#live2d-frame').count()==0
                    await browser.close()
        finally:
            proc.terminate()
            try: proc.wait(timeout=15)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            (ROOT/'artifacts/live2d-optimized-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    assert all(report['checks'].values())


if __name__=='__main__': asyncio.run(main())

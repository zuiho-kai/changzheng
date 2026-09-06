"""Real provider + broadcast page acceptance on an isolated local instance."""
import asyncio
import base64
import io
import json
from pathlib import Path
import subprocess
import time
import wave

import httpx
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:17873'

async def main():
    folder=ROOT/'artifacts'/f'runtime-live-upgrade-{int(time.time())}'
    folder.mkdir(parents=True)
    report={'profile':{'fast_model':'Qwen/Qwen3.6-35B-A3B','voice':'diana'},'turns':[],'errors':[]}
    frames=[]
    def receive(payload):
        if not isinstance(payload,str):return
        try: event=json.loads(payload)
        except ValueError:return
        if event.get('type') in ['turn_started','avatar_performance','segment','segment_committed','turn_finished','error','notice']:
            frames.append(event)
    with (folder/'server.log').open('w') as log:
        process=subprocess.Popen([str(ROOT/'.venv/Scripts/python.exe'),'probes/live2d_preview.py',
            '--port','17873','--avatar','changzheng','--data-dir',str(folder/'data')],cwd=ROOT,
            stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            async with httpx.AsyncClient(base_url=BASE,trust_env=False,timeout=10) as http:
                for _ in range(80):
                    try:
                        if (await http.get('/api/health')).is_success:break
                    except httpx.HTTPError:pass
                    if process.poll() is not None:raise RuntimeError('isolated backend exited')
                    await asyncio.sleep(.15)
                (await http.post('/api/settings',json=report['profile'])).raise_for_status()
                await http.post('/api/session',json={'scene':'live'})
                async with async_playwright() as p:
                    browser=await p.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader','--autoplay-policy=no-user-gesture-required'])
                    page=await browser.new_page(viewport={'width':1280,'height':720})
                    page.on('pageerror',lambda e:report['errors'].append(str(e)))
                    page.on('websocket',lambda ws:ws.on('framereceived',receive))
                    await page.goto(BASE+'/stage?audio=1')
                    model=page.frame_locator('#avatar').frame_locator('#live2d-frame').locator('body[data-ready=true]')
                    await model.wait_for(timeout=60000)
                    for index,text in enumerate(['你是谁呀？','你是不是又在摸鱼？','别逗了，我今天心情有点低落。']):
                        start=len(frames);sent=time.perf_counter()
                        await model.evaluate("el=>{window.seenExpressions=[];window.maxMouth=0;window.checkTimer=setInterval(()=>{window.maxMouth=Math.max(window.maxMouth,Number(el.dataset.mouth)||0);if(!window.seenExpressions.includes(el.dataset.expression))window.seenExpressions.push(el.dataset.expression)},30)}")
                        await http.post('/api/live/messages',json={'user':'小橘','text':text})
                        finished=None
                        for _ in range(160):
                            finished=next((e for e in frames[start:] if e['type']=='turn_finished'),None)
                            if finished:break
                            await asyncio.sleep(.25)
                        if not finished:raise TimeoutError('utterance did not finish')
                        await asyncio.sleep(.15)
                        events=frames[start:]
                        row={'input':text,'reply':finished['heard'],'interrupted':finished['interrupted'],
                             'metrics':finished['metrics'],'elapsed_s':round(time.perf_counter()-sent,2),
                             'max_mouth':await model.evaluate('()=>window.maxMouth'),
                             'expressions':await model.evaluate('()=>window.seenExpressions'),
                             'final_mouth':await model.get_attribute('data-mouth'),
                             'caption':await page.locator('#caption').text_content(),
                             'errors':[e.get('message') for e in events if e['type'] in ('error','notice')]}
                        await model.evaluate('()=>clearInterval(window.checkTimer)')
                        audio=[];params=None
                        for event in events:
                            if event['type']=='segment' and event.get('audio'):
                                with wave.open(io.BytesIO(base64.b64decode(event['audio'])),'rb') as wav:
                                    params=wav.getparams();audio.append(wav.readframes(wav.getnframes()))
                        if params:
                            with wave.open(str(ROOT/f'artifacts/voice-review/live-upgrade-{index+1}.wav'),'wb') as wav:
                                wav.setnchannels(params.nchannels);wav.setsampwidth(params.sampwidth);wav.setframerate(params.framerate)
                                wav.writeframes(b''.join(audio))
                        report['turns'].append(row)
                        print(json.dumps(row,ensure_ascii=False),flush=True)
                        if index==1:await page.screenshot(path=str(ROOT/'artifacts/live-upgrade-speaking.png'))
                    report['player']=(await http.get('/api/live/status')).json()
                    await browser.close()
        except Exception as exc:
            report['errors'].append(type(exc).__name__+': '+str(exc))
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)
    report['passed']=len(report['turns'])==3 and not report['errors'] and all(
        t['reply'] and not t['interrupted'] and not t['errors'] and t['max_mouth']>.1
        and float(t['final_mouth'])==0 and '[' not in t['reply'] for t in report['turns'])
    (ROOT/'artifacts/live-upgrade-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'passed':report['passed'],'errors':report['errors']},ensure_ascii=False))
    assert report['passed']

asyncio.run(main())

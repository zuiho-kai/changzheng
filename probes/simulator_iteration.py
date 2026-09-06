"""Record a candidate through the simulator's real player + observer path."""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:17874'
OUT = Path('artifacts/runtime-simulator/iterations') / (sys.argv[1] if len(sys.argv)>1 else 'candidate')
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    report = {'source': BASE, 'errors': [], 'samples': [], 'external_requests': []}
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=['--enable-unsafe-swiftshader'])
        context = await browser.new_context(viewport={'width':1280,'height':720},
            record_video_dir=str(OUT/'raw'),record_video_size={'width':1280,'height':720})
        page = await context.new_page()
        page.on('pageerror',lambda e:report['errors'].append(str(e)))
        page.on('request',lambda r:report['external_requests'].append(r.url)
            if r.url.startswith('http') and not r.url.startswith(BASE+'/') else None)
        await page.add_init_script('''Object.defineProperty(window,'AvatarPerformance',{configurable:true,set(C){Object.defineProperty(window,'AvatarPerformance',{value:C});const update=C.prototype.update;C.prototype.update=function(...args){window.testPerformer=this;window.testValues=update.apply(this,args);return window.testValues}}});''')
        await page.goto(BASE+'/stage')
        body = page.frame_locator('#avatar').frame_locator('#live2d-frame').locator('body[data-ready=true][data-mouth][data-gaze-x]')
        await body.wait_for(timeout=60000)
        await page.request.post(BASE+'/sim/action',data={'action':'reset'})
        response = await page.request.post(BASE+'/sim/action',data={'action':'scenario'})
        assert response.ok, await response.text()
        start = time.monotonic()
        while time.monotonic()-start<32:
            state = await (await page.request.get(BASE+'/sim/status')).json()
            values = await body.evaluate('''()=>({mouth:Number(document.body.dataset.mouth),fps:document.body.dataset.fps?Number(document.body.dataset.fps):null,gaze:Number(document.body.dataset.gazeX),head:window.testValues?.ParamAngleZ,body:window.testValues?.ParamBodyAngleZ,action:window.testPerformer?.action?.name,lean:window.testPerformer?.pose.lean,shoulderL:window.testPerformer?.pose.shoulderL,shoulderR:window.testPerformer?.pose.shoulderR,expression:window.testPerformer?.expression})''')
            report['samples'].append({'t':round(time.monotonic()-start,2),'state':state['status'],**values})
            await asyncio.sleep(.15)
        events = (await (await page.request.get(BASE+'/sim/status')).json())['events']
        last_start = max(i for i,e in enumerate(events) if e['detail']=='开始 30 秒排练')
        report['events'] = events[last_start:]
        await context.close()
        raw = await page.video.path()
        await browser.close()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg,'-y','-sseof','-32','-i',str(raw),'-an','-c:v','libx264',
        '-threads','2','-preset','ultrafast','-crf','21',str(OUT/'rehearsal.mp4')],capture_output=True,check=True)
    subprocess.run([ffmpeg,'-y','-i',str(OUT/'rehearsal.mp4'),'-vf',
        'fps=1,scale=320:180,tile=8x4','-frames:v','1',str(OUT/'contact.png')],capture_output=True,check=True)
    rows = report['samples']
    summary = {'states':sorted({r['state'] for r in rows}),
        'mouth_max':max(r['mouth'] for r in rows),'final_mouth':rows[-1]['mouth'],
        'completed':any(e['detail']=='排练结束' for e in report['events']),
        'natural_playback_acks':sum(e['detail']=='浏览器已确认播完' for e in report['events']),
        'interrupt_test':any(e['kind']=='打断' for e in report['events']),
        'errors':report['errors'],'external_requests':report['external_requests'],
        'lean_range':[min(r['lean'] or 0 for r in rows),max(r['lean'] or 0 for r in rows)],
        'shoulder_range':[min(r['shoulderL'] or 0 for r in rows),max(r['shoulderL'] or 0 for r in rows)]}
    report['summary'] = summary
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False))
    assert not report['errors'] and not report['external_requests'] and summary['completed']
    assert summary['natural_playback_acks']==2 and summary['mouth_max']>.1 and summary['final_mouth']==0


asyncio.run(main())

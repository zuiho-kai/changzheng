"""Record before/after in the actual stage layout, on an isolated static server.

No production websocket or player ownership. Mouth samples come from a real WAV
through WebAudio RMS. A local audio mux is for review, not a live E2E claim.
"""
import asyncio
import json
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import imageio_ffmpeg
from playwright.async_api import async_playwright
from reference_rig import Handler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/reactive-motion'
OUT.mkdir(exist_ok=True)


class MotionHandler(Handler):
    before = False
    stage = (ROOT / 'web/stage.html').read_text(encoding='utf-8').replace('<script src="/static/stage.js"></script>', '<div id="record-marker" style="position:fixed;left:0;top:0;width:8px;height:8px;background:#f00000;z-index:999"></div>')

    def do_GET(self):
        if self.path == '/stage':
            content = self.stage.encode()
        elif self.path == '/overlay':
            content = b'''<!doctype html><style>html,body,iframe{margin:0;border:0;width:100%;height:100%;background:transparent;overflow:hidden}</style><iframe id="live2d-frame" src="/static/live2d.html?model=changzheng"></iframe>'''
        elif self.path == '/static/avatar-performance.js' and self.before:
            content = (ROOT / 'artifacts/motion-before-driver.js').read_bytes()
        elif self.path == '/voice.wav':
            content = (ROOT / 'artifacts/voice-review/playful-bella.wav').read_bytes()
        else:
            return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type', 'audio/wav' if self.path.endswith('.wav') else 'text/javascript' if self.path.endswith('.js') else 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content)


async def record(browser, base, variant):
    MotionHandler.before = variant == 'before'
    ctx = await browser.new_context(viewport={'width':1280,'height':720}, record_video_dir=str(OUT/'raw'),record_video_size={'width':1280,'height':720})
    await ctx.add_init_script('''Object.defineProperty(window,'AvatarPerformance',{configurable:true,set(C){Object.defineProperty(window,'AvatarPerformance',{value:C,writable:true,configurable:true});const fn=C.prototype.update;C.prototype.update=function(t,m){window.performer=this;const v=fn.call(this,t,m);if(!window.samples)window.samples=[];if(!this.sampleAt||t-this.sampleAt>50){this.sampleAt=t;window.samples.push({t,values:v,offset:{...this.offset},action:this.action?.name,accent:!!this.accent});}return v;}}});''')
    started=time.monotonic()
    page=await ctx.new_page()
    errors=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    await page.goto(base+'/stage')
    model=page.frame_locator('#avatar').frame_locator('#live2d-frame')
    await model.locator('body[data-ready=true]').wait_for(timeout=60000)
    await page.evaluate('''async()=>{
      const model=document.querySelector('#avatar').contentWindow.document.querySelector('#live2d-frame').contentWindow;
      const send=data=>model.postMessage(data,location.origin);
      const caption=document.querySelector('#caption');
      const label=document.querySelector('.label');
      // A model message must originate from its immediate parent.
      const overlay=document.querySelector('#avatar').contentWindow;
      overlay.send=data=>overlay.document.querySelector('#live2d-frame').contentWindow.postMessage(data,location.origin);
      const ctx=new AudioContext();await ctx.resume();
      const clip=await ctx.decodeAudioData(await (await fetch('/voice.wav')).arrayBuffer());
      window.demo={ctx,clip,overlay,caption,label};
    }''')
    offset=time.monotonic()-started
    await page.evaluate('''()=>{
      const {ctx,clip,overlay,caption,label}=demo;
      const marker=document.querySelector('#record-marker');marker.style.background='#00f000';
      const send=data=>overlay.eval(`document.querySelector('#live2d-frame').contentWindow.postMessage(${JSON.stringify(data)},location.origin)`);
      const state=s=>send({type:'performance',state:s});
      const at=(ms,fn)=>setTimeout(fn,ms);
      label.textContent='动作演示 · 空闲停顿';
      at(4000,()=>{state('listening');label.textContent='接到弹幕 · 探头';});
      at(5000,()=>{
        state('speaking');label.textContent='真实语音 RMS · 说话重音';caption.textContent='嘿嘿，你猜我刚才在想什么？';
        const source=ctx.createBufferSource(),analyser=ctx.createAnalyser();analyser.fftSize=512;
        source.buffer=clip;source.connect(analyser);analyser.connect(ctx.destination);source.start();marker.style.background='#0000f0';
        const data=new Float32Array(512);let active=true;
        const pump=()=>{if(!active)return;analyser.getFloatTimeDomainData(data);const rms=Math.sqrt(data.reduce((s,x)=>s+x*x,0)/data.length);send({type:'mouth',value:Math.min(1,Math.max(0,(rms-.012)*7))});requestAnimationFrame(pump);};pump();
        source.onended=()=>{active=false;send({type:'mouth',value:0});send({type:'performance',state:'idle',reset:true});label.textContent='说完 · 缓收';caption.textContent='';marker.style.background='#00f000';};
      });
      at(7500,()=>{send({type:'performance',expression:'happy',gesture:'bounce'});label.textContent='打趣 · 短促弹一下';});
      at(8700,()=>send({type:'performance',expression:'auto'}));
      at(16000,()=>{send({type:'performance',expression:'curious',gesture:'tilt'});label.textContent='疑惑 · 偏头停一下';});
      at(18500,()=>send({type:'performance',expression:'auto'}));
      at(21000,()=>{send({type:'performance',state:'idle',reset:true});label.textContent='停止后 · 闭嘴保持自然待机';});
      at(26000,()=>{window.demoDone=true;});
    }''')
    await page.wait_for_function('window.demoDone',timeout=60000)
    rows=await model.locator('body').evaluate('()=>window.samples')
    await ctx.close()
    await page.video.save_as(str(OUT/f'{variant}.webm'))
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    marker=subprocess.run([ffmpeg,'-i',str(OUT/f'{variant}.webm'),'-vf','fps=25,crop=8:8:0:0,scale=1:1','-f','rawvideo','-pix_fmt','rgb24','-'],check=True,capture_output=True).stdout
    pixels=[marker[i:i+3] for i in range(0,len(marker),3)]
    start=next(i/25 for i,p in enumerate(pixels) if p[1]>150 and p[0]<80 and p[2]<80)
    audio=next(i/25 for i,p in enumerate(pixels) if p[2]>150 and p[0]<80 and p[1]<80)
    subprocess.run([ffmpeg,'-y','-ss',str(start),'-i',str(OUT/f'{variant}.webm'),'-itsoffset',str(audio-start),'-i',str(ROOT/'artifacts/voice-review/playful-bella.wav'),'-c:v','libx264','-threads','2','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-t','26',str(OUT/f'{variant}.mp4')],check=True,capture_output=True)
    return {'errors':errors,'samples':rows,'video_start':start,'audio_offset_seconds':audio-start}


async def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),MotionHandler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader','--autoplay-policy=no-user-gesture-required'])
            reports={}
            for variant in ['before','after']:
                reports[variant]=await record(browser,f'http://127.0.0.1:{server.server_port}',variant)
            await browser.close()
        (OUT/'samples.json').write_text(json.dumps(reports),encoding='utf-8')
        rows=reports['after']['samples']
        checks={'no_page_errors':all(not r['errors'] for r in reports.values()),'yaw_zero':all(r['values']['ParamAngleX']==0 for r in rows),'mouth_driven_by_real_audio':max(r['values']['ParamMouthOpenY'] for r in rows)>.15,'closed_at_end':all(r['values']['ParamMouthOpenY']==0 for r in rows[-20:]),'bounce_reaches_root':min(r['offset']['y'] for r in rows)<-.01,'real_audio_has_accents':any(r['accent'] for r in rows),'bounce_settles':max(abs(r['offset']['y']) for r in rows[-20:])<.0001}
        (OUT/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
        print(json.dumps(checks,indent=2))
        assert all(checks.values())
    finally:
        server.shutdown();server.server_close()


if __name__=='__main__':asyncio.run(main())

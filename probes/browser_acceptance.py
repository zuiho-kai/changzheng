"""Real browser playback and synthetic microphone through real ASR/models.

No physical microphone/speaker latency claim. Browser audio graph is instrumented.
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from companion.providers import Provider

BASE='http://127.0.0.1:17862'


async def main():
    provider=Provider()
    audio,_=await provider.speech('先别说了，请记住，我工作时喜欢喝无糖绿茶。')
    await provider.close()
    encoded=base64.b64encode(audio).decode()
    report={'checks':{},'boundary':'Synthetic MediaStream into real browser VAD, real remote ASR/TTS/chat. No physical microphone or acoustic latency measurement.'}
    async with httpx.AsyncClient(base_url=BASE,timeout=60) as client:
        await client.post('/api/session',json={'scene':'work'})
        await client.post('/api/settings',json={'auto_memory':True,'audio_enabled':True})
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
            page=await browser.new_page(viewport={'width':1180,'height':850})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            await page.add_init_script('''
              window.audit={events:[],sent:[],starts:[],stops:[]};
              const NativeWS=WebSocket;
              window.WebSocket=class extends NativeWS {
                constructor(...args){super(...args);this.addEventListener('message',e=>{audit.events.push(JSON.parse(e.data));});}
                send(data){audit.sent.push({at:performance.now(),...JSON.parse(data)});return super.send(data);}
              };
              const start=AudioBufferSourceNode.prototype.start, stop=AudioBufferSourceNode.prototype.stop;
              AudioBufferSourceNode.prototype.start=function(...args){audit.starts.push({at:performance.now(),duration:this.buffer?.duration});return start.apply(this,args);};
              AudioBufferSourceNode.prototype.stop=function(...args){audit.stops.push({at:performance.now()});return stop.apply(this,args);};
            ''')
            await page.goto(BASE)
            await page.wait_for_function("document.querySelector('#connection').textContent==='已连接'")
            await page.locator('#message').fill('请原样说这两句话：我先查看日志。接下来紫色火箭将穿过遥远的星云。')
            await page.locator('#chat-form .send-button').click()
            await page.wait_for_function('audit.starts.length>=2',timeout=60000)
            await page.wait_for_timeout(150)
            await page.locator('#stop-button').click()
            await page.wait_for_function("audit.events.some(e=>e.type==='turn_finished'&&e.interrupted)",timeout=10000)
            await page.wait_for_timeout(1000)
            audit=await page.evaluate('audit')
            finished=next(e for e in audit['events'] if e['type']=='turn_finished' and e['interrupted'])
            segments=[e for e in audit['events'] if e['type']=='segment' and e['turn_id']==finished['turn_id']]
            acks=[e for e in audit['sent'] if e['type']=='played' and e['turn_id']==finished['turn_id']]
            expected=''.join(e['text'] for e in segments if any(a['id']==e['id'] for a in acks))
            report['checks']['natural_playback_ack']=bool(acks)
            report['checks']['stopped_segment_not_committed']=len(acks)<len(segments) and finished['heard']==expected
            report['checks']['audio_source_actually_stopped']=bool(audit['stops'])
            report['metrics']=finished['metrics']
            await page.locator('#message').fill('刚才说到哪里了？')
            await page.locator('#chat-form .send-button').click()
            await page.wait_for_function('audit.events.filter(e=>e.type==="turn_started").length>=2',timeout=10000)
            await page.wait_for_timeout(1500)
            context=(await client.get('/api/context')).json()['messages']
            report['checks']['real_next_context_uses_played_prefix']=[x['content'] for x in context if x['role']=='assistant']==[expected]
            await page.locator('#stop-button').click()
            # Replace only the hardware boundary. VAD/WAV upload/ASR/chat remain real.
            await page.evaluate('''encoded=>{
              navigator.mediaDevices.getUserMedia=async()=>{
                const ctx=new AudioContext(); await ctx.resume();
                const dest=ctx.createMediaStreamDestination();
                const source=ctx.createBufferSource();
                source.buffer=await ctx.decodeAudioData(Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)).buffer);
                source.connect(dest);source.start(ctx.currentTime+.5);
                window.syntheticMic={ctx,source,dest};return dest.stream;
              };
            }''',encoded)
            await page.locator('#mic-button').click()
            await page.wait_for_function("audit.events.some(e=>e.type==='user_message'&&e.message.content.includes('绿茶'))",timeout=60000)
            await page.locator('#mic-button').click()
            report['checks']['synthetic_mic_vad_real_asr_user_message']=True
            await page.wait_for_function("audit.events.some(e=>e.type==='memories_updated'&&e.memories.some(m=>m.content.includes('绿茶')))",timeout=60000)
            report['checks']['spoken_preference_auto_memory']=True
            await page.locator('#stop-button').click()
            await page.screenshot(path=str(ROOT/'artifacts/browser-acceptance.png'))
            report['checks']['no_browser_errors']=not errors
            report['errors']=errors
            await browser.close()
    (ROOT/'artifacts/browser-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    assert all(report['checks'].values())


if __name__=='__main__':asyncio.run(main())

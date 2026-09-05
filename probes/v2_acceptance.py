"""Real local word boundaries, interruption, task notices, live flood."""
import asyncio
import json
import time
from pathlib import Path
import httpx
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:17862'


async def main():
    report={'checks':{},'metrics':{},'boundary':'SAPI engine timestamps plus browser estimated output clock; not a physical hearing measurement.'}
    async with httpx.AsyncClient(base_url=BASE,timeout=60) as client:
        async def post(path,data):
            r=await client.post(path,json=data);r.raise_for_status();return r.json()
        await post('/api/settings',{'voice':'local:Microsoft Huihui Desktop','auto_memory':False,'audio_enabled':True})
        await post('/api/session',{'scene':'work'})
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
            page=await browser.new_page(viewport={'width':1180,'height':850})
            errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
            await page.add_init_script('''
                window.audit={events:[],sent:[]};const Real=WebSocket;
                window.WebSocket=class extends Real {
                    constructor(...a){super(...a);this.addEventListener('message',e=>audit.events.push(JSON.parse(e.data)));}
                    send(s){audit.sent.push({at:performance.now(),...JSON.parse(s)});super.send(s);}
                };
            ''')
            await page.goto(BASE)
            await page.wait_for_function("document.querySelector('#connection').textContent==='已连接'")
            await page.locator('#message').fill('请原样读一句话：我先查看日志，然后再讨论下一步。')
            await page.locator('#chat-form .send-button').click()
            await page.wait_for_function("audit.events.filter(e=>e.type==='segment_committed'&&e.partial).length>=2",timeout=60000)
            await page.screenshot(path=str(ROOT/'artifacts/word-progress.png'))
            await page.locator('#stop-button').click()
            await page.wait_for_function("audit.events.some(e=>e.type==='turn_finished'&&e.interrupted)",timeout=10000)
            audit=await page.evaluate('audit')
            finished=next(e for e in audit['events'] if e['type']=='turn_finished' and e['interrupted'])
            segment=next(e for e in audit['events'] if e['type']=='segment' and e['turn_id']==finished['turn_id'])
            report['checks']['real_engine_word_boundaries']=bool(segment['boundaries'])
            report['checks']['interruption_retains_partial_segment']=0<len(finished['heard'])<len(segment['text']) and segment['text'].startswith(finished['heard'])
            report['checks']['stop_includes_actual_cursor']=any(e['type']=='interrupt' and e.get('progress',{}).get('turn_id')==finished['turn_id'] for e in audit['sent'])
            report['heard_prefix']=finished['heard'];report['metrics']['word_turn']=finished['metrics']
            await page.evaluate('window.secondStart=audit.events.length')
            await page.locator('#message').fill('现在先不要继续，回答收到就好。')
            await page.locator('#chat-form .send-button').click()
            await page.wait_for_function("audit.events.slice(secondStart).some(e=>e.type==='segment')",timeout=60000)
            context=(await client.get('/api/context')).json()['messages']
            report['checks']['partial_prefix_in_actual_next_model_input']=[m['content'] for m in context if m['role']=='assistant']==[finished['heard']]
            await page.locator('#stop-button').click()
            await page.wait_for_function("audit.events.slice(secondStart).some(e=>e.type==='turn_finished')",timeout=10000)

            # Clear the explicit Stop block with an ordinary owner turn, then
            # demonstrate task completion announced automatically at idle.
            await page.evaluate('window.thirdStart=audit.events.length')
            await page.locator('#message').fill('回答一个字：好')
            await page.locator('#chat-form .send-button').click()
            await page.wait_for_function("audit.events.slice(thirdStart).some(e=>e.type==='turn_finished'&&!e.interrupted)",timeout=60000)
            folder=ROOT/'artifacts/runtime-v2'; marker='NOTICE-'+str(time.time_ns());(folder/'notice.txt').write_text(marker)
            task=await post('/api/tasks',{'prompt':'使用命令读取notice.txt，只返回文件内容。','cwd':str(folder),'read_only':True})
            print('Waiting for real task completion and spoken notice',flush=True)
            await page.wait_for_function("audit.events.some(e=>e.type==='task_updated'&&e.task.id===taskId&&e.task.status==='completed')".replace('taskId',json.dumps(task['id'])),timeout=180000)
            await page.wait_for_function("audit.events.some(e=>e.type==='turn_finished'&&e.metrics?.source==='task_notice'&&!e.interrupted)",timeout=60000)
            audit=await page.evaluate('audit')
            report['checks']['real_codex_task_complete']=any(e['type']=='task_updated' and e['task']['id']==task['id'] and marker in e['task']['summary'] for e in audit['events'])
            notice=next(e for e in audit['events'] if e['type']=='turn_finished' and e['metrics'].get('source')=='task_notice' and not e['interrupted'])
            report['checks']['completion_spoken_at_idle']=bool(notice['heard'])

            await page.locator('[data-scene="live"]').click()
            await page.wait_for_function("document.querySelector('[data-scene=live]').classList.contains('active')")
            start=time.monotonic();responses=[]
            # Incoming pressure is independent of playback speed.
            for batch in range(20):
                responses.extend(await asyncio.gather(*[post('/api/live/messages',{'user':f'观众{i}', 'text':f'话题{batch}-{i}：今天给小猫起什么名字？'}) for i in range(10)]))
                await asyncio.sleep(.15)
            await page.wait_for_timeout(14000)
            audit=await page.evaluate('audit')
            live=[e for e in audit['events'] if e['type']=='turn_finished' and e.get('metrics',{}).get('source')=='live']
            report['checks']['live_buffer_bounded']=max(r['buffered'] for r in responses)<=100
            report['checks']['live_not_one_reply_per_message']=0<len(live)<20
            report['checks']['live_utterance_budget']=all(len(e['heard'])<=e['metrics']['speech_budget'] for e in live)
            report['metrics']['live_input_count']=200
            report['metrics']['live_completed_replies']=len(live)
            report['metrics']['live_elapsed_s']=round(time.monotonic()-start,2)
            report['metrics']['live_turns']=[e['metrics'] for e in live]
            await page.locator('#stop-button').click()
            report['checks']['no_browser_errors']=not errors;report['errors']=errors
            await browser.close()
    (ROOT/'artifacts/v2-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    assert all(report['checks'].values())


if __name__=='__main__':asyncio.run(main())

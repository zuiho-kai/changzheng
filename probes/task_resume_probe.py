import asyncio
import json
from pathlib import Path
import httpx
import websockets

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:17862'


async def main():
    checks={}
    async with httpx.AsyncClient(base_url=BASE,timeout=60) as c:
        async with websockets.connect(BASE.replace('http:','ws:')+'/ws',origin=BASE) as ws:
            await ws.recv()
            r=await c.post('/api/tasks',json={'prompt':'先使用命令等待15秒，然后读取当前目录fixture.txt。只报告文件内容。','cwd':str(ROOT/'artifacts/runtime-acceptance'),'read_only':True})
            r.raise_for_status(); task=r.json()
            for _ in range(100):
                event=json.loads(await asyncio.wait_for(ws.recv(),90))
                if event['type']=='task_progress' and event.get('task_id')==task['id'] and event['text']=='正在执行命令':break
                if event['type']=='task_updated' and event['task']['id']==task['id'] and event['task']['status']=='failed':raise RuntimeError(event['task']['summary'])
            else:raise RuntimeError('No command execution observed')
            checks['actual_command_started']=True
            print('Command executing; requesting pause',flush=True)
            r=await c.post('/api/tasks/'+task['id']+'/pause'); r.raise_for_status()
            for _ in range(30):
                current=next(x for x in (await c.get('/api/state')).json()['tasks'] if x['id']==task['id'])
                if current['status']=='paused':break
                await asyncio.sleep(.3)
            checks['actual_turn_interrupted']=current['status']=='paused'
            # Ordinary speech Stop and task pause are separate controls.
            await ws.send(json.dumps({'type':'interrupt'}))
            r=await c.post('/api/tasks/'+task['id']+'/resume'); r.raise_for_status()
            print('Resumed same task/thread',flush=True)
            for _ in range(100):
                current=next(x for x in (await c.get('/api/state')).json()['tasks'] if x['id']==task['id'])
                if current['status'] in ('completed','failed'):break
                await asyncio.sleep(2)
            marker=(ROOT/'artifacts/runtime-acceptance/fixture.txt').read_text()
            checks['resumed_task_completed_read']=current['status']=='completed' and marker in current['summary']
            checks['same_thread_resumed']=bool(current['thread_id']) and len([x for x in (await c.get('/api/state')).json()['tasks'] if x['id']==task['id']])==1
    result={'checks':checks,'status':current['status'],'note':'Real read-only command interrupted, same task resumed and fixture read. Does not establish exactly-once behavior for arbitrary side effects.'}
    (ROOT/'artifacts/task-resume-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    assert all(checks.values())


if __name__=='__main__':asyncio.run(main())

"""Real local HTTP/WS + provider + Codex acceptance, synthetic data only."""
import asyncio
import io
import json
import sys
import time
import wave
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:17862'


async def main():
    report = {'checks': {}, 'metrics': {}}
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as client:
        async def post(path, value):
            r = await client.post(path, json=value); r.raise_for_status(); return r.json()
        await post('/api/settings', {'auto_memory': False})
        await post('/api/session', {'scene': 'work'})
        for old in (await client.get('/api/memories')).json():
            await client.delete('/api/memories/'+old['id'])
        fact = await post('/api/memories', {'content':'用户工作时喜欢喝美式咖啡，提神保持专注', 'scene':'work','visibility':'private'})
        rec = (await client.get('/api/recall',params={'q':'干活困了，给我推荐一种饮料','scene':'work'})).json()
        report['checks']['real_semantic_recall'] = any(x['id']==fact['id'] for x in rec)
        public = (await client.get('/api/recall',params={'q':'工作咖啡提神','scene':'live'})).json()
        report['checks']['private_memory_excluded_live'] = not public
        async with websockets.connect(BASE.replace('http:','ws:')+'/ws', origin=BASE) as ws:
            await ws.recv()
            await ws.send(json.dumps({'type':'message','voice':True,'text':'请原样读出以下两句话，不要增加内容：我先查看日志。紫色火箭马上起飞。'}))
            segments=[]
            while True:
                event=json.loads(await asyncio.wait_for(ws.recv(),60))
                if event['type']=='error': raise RuntimeError(event['message'])
                if event['type']=='segment':
                    segments.append(event)
                    if len(segments)==2: break
            first, second=segments[:2]
            import base64
            with wave.open(io.BytesIO(base64.b64decode(first['audio'])),'rb') as wav:
                report['checks']['real_tts_decodable'] = wav.getnframes()>1000
            await ws.send(json.dumps({'type':'played','turn_id':first['turn_id'],'id':first['id']}))
            await ws.send(json.dumps({'type':'interrupt'}))
            while True:
                event=json.loads(await asyncio.wait_for(ws.recv(),20))
                if event['type']=='turn_finished':
                    report['metrics']['first_turn']=event['metrics']; break
            history=(await client.get('/api/state')).json()['history']
            assistants=[x['content'] for x in history if x['role']=='assistant']
            report['checks']['interrupted_history_exact_prefix']=assistants==[first['text']]
            # Source user asked the full quote, so only compare assistant-role context.
            await ws.send(json.dumps({'type':'message','voice':False,'text':'你刚才实际说到哪里了？只复述已说出的部分。'}))
            while True:
                event=json.loads(await asyncio.wait_for(ws.recv(),60))
                if event['type']=='error': raise RuntimeError(event['message'])
                if event['type']=='segment':
                    actual=(await client.get('/api/context')).json()['messages']
                    spoken=[x['content'] for x in actual if x['role']=='assistant']
                    report['checks']['actual_next_request_exact_spoken_prefix']=spoken==[first['text']]
                    await ws.send(json.dumps({'type':'interrupt'})); break
        r=await client.put('/api/memories/'+fact['id'],json={'content':'用户工作时偏好无糖绿茶'}); r.raise_for_status()
        rec=(await client.get('/api/recall',params={'q':'工作喝什么饮料','scene':'work'})).json()
        report['checks']['correction_recalled']=any(x['content']=='用户工作时偏好无糖绿茶' for x in rec)
        await client.delete('/api/memories/'+fact['id'])
        report['checks']['deleted_not_recalled']=not (await client.get('/api/recall',params={'q':'工作饮料绿茶','scene':'work'})).json()
        audio=(ROOT/'artifacts/voice-sample.wav').read_bytes()
        r=await client.post('/api/transcribe',content=audio,headers={'content-type':'audio/wav'}); r.raise_for_status()
        report['checks']['real_asr_roundtrip']=bool(r.json()['text'])
        report['metrics']['asr_ms']=r.json()['asr_ms']
        fixture=ROOT/'artifacts/runtime-acceptance/fixture.txt'; fixture.parent.mkdir(parents=True,exist_ok=True)
        marker='CZ-'+str(time.time_ns()); fixture.write_text(marker,encoding='utf-8')
        task=await post('/api/tasks',{'prompt':'使用命令读取当前目录 fixture.txt，最终只返回文件里的内容。','cwd':str(fixture.parent),'read_only':True})
        print('Real Codex task dispatched', flush=True)
        for _ in range(120):
            tasks=(await client.get('/api/state')).json()['tasks']
            current=next(x for x in tasks if x['id']==task['id'])
            if current['status'] in ('completed','failed','paused'):break
            await asyncio.sleep(2)
        report['checks']['codex_actual_file_read']=current['status']=='completed' and marker in current['summary']
        report['codex_task_status']=current['status']
    path=ROOT/'artifacts/runtime-probe.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    assert all(report['checks'].values()), 'Acceptance failed; see report'


if __name__=='__main__': asyncio.run(main())

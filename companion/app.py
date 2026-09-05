import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .codex import CodexBridge
from .providers import Provider
from .runtime import Runtime
from .secrets import data_dir, get_key, save_key
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = {}
OWNER = None
store = None
runtime = None
bridge = None
provider = None


async def emit(event):
    global OWNER
    dead = []
    for ws, role in list(CLIENTS.items()):
        outgoing = event
        if role == 'observer':
            if event['type'] == 'state':
                outgoing = {'type':'state', 'scene':runtime.scene, 'status':'idle',
                    'settings':{'avatar':runtime.settings()['avatar']}}
            elif runtime.scene != 'live' or event['type'] not in ('status', 'turn_started', 'segment_committed', 'turn_finished'):
                continue
        try:
            await ws.send_json(outgoing)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CLIENTS.pop(ws, None)
        if OWNER is ws:
            OWNER = None


@asynccontextmanager
async def lifespan(app):
    global store, runtime, bridge, provider
    store = Store(data_dir() / 'companion.db')
    for task in store.tasks():
        if task['status'] in ('queued', 'running', 'pausing'):
            store.update_task(task['id'], status='paused', summary=task['summary'] or '上次运行已结束，可继续任务')
    provider = Provider()
    runtime = Runtime(store, provider, emit)
    bridge = CodexBridge(store, emit)
    runtime.dispatch_task = bridge.launch
    yield
    await runtime.close()
    await bridge.close()
    await provider.close()
    store.close()


app = FastAPI(lifespan=lifespan)


def origin_allowed(origin, host):
    if not origin:
        return True
    parsed = urlparse(origin)
    return parsed.scheme == 'http' and parsed.netloc == host


@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.headers.get('host', '')
    if host.split(':')[0] not in ('127.0.0.1', 'localhost', '[::1]'):
        return JSONResponse({'detail': 'Local access only'}, 403)
    if request.method not in ('GET', 'HEAD') and not origin_allowed(request.headers.get('origin'), host):
        return JSONResponse({'detail': 'Origin rejected'}, 403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def value_error(request, exc):
    return JSONResponse({'detail': str(exc)}, 400)


@app.exception_handler(KeyError)
async def missing_item(request, exc):
    return JSONResponse({'detail': '记录不存在'}, 404)


@app.get('/api/health')
async def health():
    return {'ok': True, 'app': 'changzheng', 'version': '0.1.0'}


@app.get('/api/state')
async def state():
    return {**runtime.state(), 'key_configured': bool(get_key())}


@app.post('/api/settings')
async def settings(request: Request):
    data = await request.json()
    if data.get('api_key'):
        save_key(data['api_key'])
    choices = {'fast_model', 'voice', 'cwd', 'audio_enabled', 'auto_memory'}
    for key in choices & data.keys():
        value = data[key]
        if key == 'voice' and value not in ('claire','anna','bella','diana','alex','benjamin','charles','david'):
            raise ValueError('音色不存在')
        if key == 'cwd':
            path = Path(value).expanduser().resolve()
            if not path.is_dir():
                raise ValueError('工作目录不存在')
            value = str(path)
        store.set_setting(key, value)
    return await state()


@app.post('/api/session')
async def session(request: Request):
    body = await request.json()
    scene = body.get('scene', runtime.scene)
    if scene not in ('chat','work','live'):
        raise ValueError('场景不存在')
    await runtime.new_session(scene)
    return await state()


@app.post('/api/transcribe')
async def transcribe(request: Request):
    data = await request.body()
    if len(data) > 8_000_000 or len(data) < 44:
        raise ValueError('语音长度不合适，请说短一些')
    start = time.perf_counter()
    try:
        text = await provider.transcribe(data)
    except Exception as exc:
        raise HTTPException(502, str(exc)[:250]) from exc
    return {'text': text, 'asr_ms': round((time.perf_counter()-start)*1000)}


@app.get('/api/memories')
async def memories():
    return store.memories()


@app.post('/api/memories')
async def remember(request: Request):
    body = await request.json()
    return store.add_memory(str(body.get('content',''))[:2000], scene=body.get('scene','all'),
        visibility=body.get('visibility','private'), source_id=body.get('source_id'), kind=body.get('kind','fact'))


@app.put('/api/memories/{memory_id}')
async def correct(memory_id: str, request: Request):
    body = await request.json()
    await runtime.invalidate_memory()
    result = store.update_memory(memory_id, str(body.get('content',''))[:2000],
        scene=body.get('scene'), visibility=body.get('visibility'))
    await emit({'type':'state', **runtime.state()})
    return result


@app.delete('/api/memories/{memory_id}')
async def forget(memory_id: str):
    await runtime.invalidate_memory()
    store.forget_memory(memory_id)
    await emit({'type':'state', **runtime.state()})
    return {'ok':True}


@app.get('/api/recall')
async def recall(q: str, scene: str='chat'):
    try:
        return await asyncio.wait_for(runtime.memory_search.recall(q, scene), timeout=3)
    except Exception:
        return store.recall(q, scene=scene)


@app.post('/api/live/messages')
async def live_message(request: Request):
    body = await request.json()
    return await runtime.live_message(body.get('user','观众'), str(body.get('text','')))


@app.post('/api/tasks')
async def task(request: Request):
    body = await request.json()
    prompt = str(body.get('prompt','')).strip()[:12000]
    if not prompt:
        raise ValueError('请输入任务')
    cwd = str(Path(body.get('cwd') or runtime.settings()['cwd']).resolve())
    if not Path(cwd).is_dir():
        raise ValueError('工作目录不存在')
    result = await bridge.launch(prompt, cwd, read_only=bool(body.get('read_only',False)))
    await emit({'type':'task_updated','task':result})
    return result


@app.post('/api/tasks/{task_id}/pause')
async def pause(task_id: str):
    return await bridge.pause(task_id)


@app.post('/api/tasks/{task_id}/resume')
async def resume(task_id: str):
    task = next((x for x in store.tasks() if x['id']==task_id), None)
    if not task:
        raise HTTPException(404, '任务不存在')
    result = await bridge.launch('继续原任务。先核对已完成动作和实际状态，不重复执行。原任务：'+task['prompt'], task['cwd'],task_id=task_id)
    await emit({'type':'task_updated','task':result})
    return result


@app.post('/api/approval')
async def approval(request: Request):
    body = await request.json()
    await bridge.approve(str(body['request_id']), body.get('accepted') is True)
    return {'ok':True}


@app.post('/api/avatar')
async def avatar(request: Request):
    extension = request.query_params.get('ext','').lower()
    if extension not in ('gif','png','webp','apng'):
        raise ValueError('请选择 GIF、APNG、PNG 或 WebP 图片')
    data = await request.body()
    if len(data)>20_000_000:
        raise ValueError('图片请小于20MB')
    import io
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width*im.height > 30_000_000:
                raise ValueError('图片尺寸过大')
            im.verify()
    except Exception as exc:
        raise ValueError('无法读取这张图片') from exc
    folder = data_dir()/'avatars'
    folder.mkdir(parents=True,exist_ok=True)
    name = uuid.uuid4().hex+'.'+extension
    (folder/name).write_bytes(data)
    store.set_setting('avatar','/avatars/'+name)
    return {'avatar':'/avatars/'+name}


@app.get('/avatars/{name}')
async def get_avatar(name:str):
    if Path(name).name!=name:
        raise HTTPException(404)
    path=data_dir()/'avatars'/name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.get('/api/context')
async def context_audit():
    if os.environ.get('CHANGZHENG_AUDIT')!='1':
        raise HTTPException(404)
    return {'messages':runtime.last_context,'pending_count':len(runtime.ledger.pending),
        'heard':runtime.ledger.heard,'turn_id':runtime.ledger.turn_id}


@app.websocket('/ws')
async def socket(ws: WebSocket):
    global OWNER
    host = ws.headers.get('host','')
    if host.split(':')[0] not in ('127.0.0.1', 'localhost') or not origin_allowed(ws.headers.get('origin'),host):
        await ws.close(code=1008)
        return
    role = 'observer' if ws.query_params.get('role')=='observer' else 'control'
    await ws.accept()
    if role=='control' and OWNER is not None:
        await ws.send_json({'type':'error','message':'另一个窗口正在控制对话，请先关闭它。'})
        await ws.close(code=1008)
        return
    if role=='control':
        OWNER=ws
    CLIENTS[ws]=role
    await ws.send_json({'type':'state', **(runtime.state() if role=='control' else {'scene':runtime.scene,'status':runtime.status if runtime.scene=='live' else 'idle','settings':{'avatar':runtime.settings()['avatar']}})})
    try:
        while True:
            body=await ws.receive_json()
            if role!='control':
                continue
            kind=body.get('type')
            if kind=='message':
                await runtime.message(str(body.get('text','')),voice=body.get('voice',True))
            elif kind=='interrupt':
                # Completed ACKs can be included atomically with the stop event.
                for ack in body.get('completed',[])[:20]:
                    await runtime.ack(ack.get('turn_id'),ack.get('id'))
                await runtime.interrupt()
            elif kind=='played':
                await runtime.ack(body.get('turn_id'),body.get('id'))
            elif kind=='playback_started':
                if body.get('turn_id')==runtime.ledger.turn_id and 'audible_wait_ms' not in runtime.metrics:
                    runtime.metrics['audible_wait_ms']=round((time.time()-runtime.metrics.get('received_at',time.time()))*1000)
            elif kind=='ping':
                await ws.send_json({'type':'pong'})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        CLIENTS.pop(ws,None)
        if OWNER is ws:
            OWNER=None
            await runtime.interrupt()


@app.get('/')
async def index():
    return FileResponse(ROOT/'web/index.html')


@app.get('/overlay')
async def overlay():
    return FileResponse(ROOT/'web/index.html')


app.mount('/static', StaticFiles(directory=ROOT/'web',check_dir=False), name='static')

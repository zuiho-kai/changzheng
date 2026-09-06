"""Offline rehearsal host. Deliberately does not import companion runtime/providers."""
import asyncio
import base64
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'simulator'
WORK = HERE / 'workspace'
OUTPUT = ROOT / 'artifacts/runtime-simulator'
OUTPUT.mkdir(parents=True, exist_ok=True)
if not WORK.exists():
    shutil.copytree(ROOT / 'web', WORK)
CLIPS = {
    'curious': ('哎？你说的那个，我还真没见过。快讲讲，后来呢？', 'curious', 'audition-diana-curious.wav'),
    'tease': ('等一下，说谁呆呢？我刚才那叫深思熟虑。好吧，其实在发呆。', 'happy', 'audition-diana-tease.wav'),
    'comfort': ('低落的话就静默陪着吧。不用勉强笑，我就在这，不吵你。', 'neutral', 'live-upgrade-3.wav'),
}
app = FastAPI()
clients = {}
owner = None
status = 'idle'
audio_state = 'uninitialized'
turn = None
heard = ''
messages = []
events = []
scenario = None
recording = {'state': 'idle'}
speech_done = asyncio.Event()


def log(kind, detail):
    events.append({'time': time.strftime('%H:%M:%S'), 'kind': kind, 'detail': detail})
    del events[:-80]


async def emit(event, observers_only=False):
    for ws, role in list(clients.items()):
        if observers_only and role != 'observer':
            continue
        if event['type'] == 'segment' and role == 'observer':
            continue
        try:
            await ws.send_json(event)
        except Exception:
            pass


def state():
    return dict(type='state', scene='live', status=status, turn_id=turn, heard=heard,
                settings={'avatar': 'live2d:changzheng', 'audio_enabled': True})


async def set_status(value):
    global status
    status = value
    await emit({'type': 'status', 'status': value})
    log('状态', value)


async def stop():
    global turn, heard
    old = turn
    turn = None
    heard = ''
    await emit({'type': 'turn_finished', 'turn_id': old, 'interrupted': True, 'heard': ''})
    await set_status('idle')
    speech_done.set()


async def chat(user, text):
    messages.append({'user': user, 'text': text, 'event_id': uuid.uuid4().hex})
    del messages[:-20]
    log('弹幕', f'{user}：{text}')


async def speak(key):
    global turn, heard
    if key not in CLIPS:
        raise HTTPException(400, '请选择测试语音')
    if owner is None or audio_state != 'running':
        raise HTTPException(409, '请先在预览中点击启用声音')
    await stop()
    text, expression, filename = CLIPS[key]
    audio = (ROOT / 'artifacts/voice-review' / filename).read_bytes()
    turn = uuid.uuid4().hex
    heard = text
    speech_done.clear()
    await emit({'type': 'turn_started', 'turn_id': turn})
    await emit({'type': 'avatar_performance', 'turn_id': turn, 'expression': expression})
    await emit({'type': 'segment', 'turn_id': turn, 'id': 'sample', 'text': text,
                'audio': base64.b64encode(audio).decode()})
    log('语音', key + ' · 已有录音，无在线生成')


async def run_scenario():
    try:
        log('剧本', '开始 30 秒排练')
        await stop()
        await asyncio.sleep(5)
        await chat('路过的小橘', '小征在看哪里？')
        await set_status('listening')
        await asyncio.sleep(2)
        await set_status('thinking')
        await asyncio.sleep(2)
        await speak('curious')
        await asyncio.sleep(8)
        await chat('摸鱼观众', '你是不是又在发呆？')
        await speak('tease')
        await asyncio.sleep(2)
        await stop()
        log('打断', '旧音频停止，嘴型归零')
        await asyncio.sleep(3)
        await speak('comfort')
        await asyncio.sleep(8)
        await stop()
        log('剧本', '排练结束')
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log('错误', str(exc))
        await stop()


async def cancel_scenario():
    global scenario
    if scenario and not scenario.done():
        scenario.cancel()
        try:
            await scenario
        except asyncio.CancelledError:
            pass
    scenario = None


@app.get('/api/health')
async def health():
    return {'ok': True, 'mode': 'offline-simulator'}


@app.get('/api/live/status')
async def live_status():
    return dict(scene='live', status=status, connected=True, player_connected=owner is not None,
                audio_enabled=True, audio_state=audio_state, messages=messages, attention=[])


@app.get('/sim/status')
async def sim_status():
    return dict(status=status, audio_state=audio_state, player_connected=owner is not None,
                events=events, recording=recording, scenario=bool(scenario and not scenario.done()),
                workspace=str(WORK))


@app.post('/sim/action')
async def action(data: dict):
    global scenario
    kind = data.get('action')
    if kind == 'chat':
        text = str(data.get('text', '')).strip()[:300]
        if not text:
            raise HTTPException(400, '请输入弹幕')
        await chat(str(data.get('user', '模拟观众'))[:30], text)
    elif kind == 'expression':
        expression = data.get('value')
        if expression not in ('neutral', 'happy', 'curious', 'surprised', 'serious'):
            raise HTTPException(400, '未知表情')
        await emit({'type': 'avatar_performance', 'turn_id': turn, 'expression': expression})
        log('表情', expression)
    elif kind in ('state', 'stop', 'reset', 'voice', 'scenario'):
        await cancel_scenario()
        await stop()
        if kind == 'state':
            value = data.get('value')
            if value not in ('idle', 'listening', 'thinking'):
                raise HTTPException(400, '说话请使用真实测试语音')
            await set_status(value)
        elif kind == 'reset':
            messages.clear()
            log('重置', '弹幕和播音已清空')
        elif kind == 'voice':
            await speak(data.get('value'))
        elif kind == 'scenario':
            if audio_state != 'running':
                raise HTTPException(409, '请先启用声音，再开始排练')
            scenario = asyncio.create_task(run_scenario())
    else:
        raise HTTPException(400, '未知操作')
    return {'ok': True}


@app.websocket('/ws')
async def websocket(ws: WebSocket):
    global owner, audio_state, turn
    await ws.accept()
    role = ws.query_params.get('role', 'player')
    if role != 'observer' and owner is not None:
        await ws.close(code=1008)
        return
    clients[ws] = role
    if role != 'observer':
        owner = ws
    await ws.send_json(state())
    try:
        while True:
            data = await ws.receive_json()
            if ws is not owner:
                continue
            kind = data.get('type')
            if kind == 'player_audio_state':
                audio_state = data.get('state', 'uninitialized')
            elif kind == 'interrupt':
                await stop()
            elif data.get('turn_id') == turn and turn:
                if kind == 'mouth':
                    await emit(data, observers_only=True)
                elif kind == 'playback_started':
                    await set_status('speaking')
                    await emit({'type': 'segment_committed', 'turn_id': turn, 'heard': heard})
                    log('播放', '浏览器已开始播放')
                elif kind == 'played':
                    await emit({'type': 'turn_finished', 'turn_id': turn, 'heard': heard})
                    turn = None
                    await set_status('idle')
                    speech_done.set()
                    log('播放', '浏览器已确认播完')
    except WebSocketDisconnect:
        pass
    finally:
        clients.pop(ws, None)
        if owner is ws:
            owner = None
            audio_state = 'disconnected'
            await cancel_scenario()
            await stop()


async def record_stage():
    """Record a separate observer of this simulator; it cannot own audio."""
    global recording
    name = time.strftime('rehearsal-%Y%m%d-%H%M%S')
    try:
        from playwright.async_api import async_playwright
        import imageio_ffmpeg
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=['--enable-unsafe-swiftshader'])
            try:
                context = await browser.new_context(viewport={'width': 1280, 'height': 720},
                    record_video_dir=str(OUTPUT / name), record_video_size={'width': 1280, 'height': 720})
                page = await context.new_page()
                await page.goto(f'http://127.0.0.1:{PORT}/stage')
                await page.frame_locator('#avatar').frame_locator('#live2d-frame').locator('body[data-ready=true]').wait_for(timeout=60000)
                recording = {'state': 'recording', 'remaining': 30}
                for remaining in range(30, 0, -1):
                    recording['remaining'] = remaining
                    await asyncio.sleep(1)
                await context.close()
                raw = await page.video.path()
                recording = {'state': 'saving'}
            finally:
                await browser.close()
        result = await asyncio.to_thread(subprocess.run, [imageio_ffmpeg.get_ffmpeg_exe(),
            '-y', '-sseof', '-30', '-i', str(raw), '-an', '-c:v', 'libx264', '-threads', '2',
            '-preset', 'ultrafast', '-crf', '21', str(OUTPUT / f'{name}.mp4')],
            capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace')[-600:])
        recording = {'state': 'done', 'url': f'/recordings/{name}.mp4'}
        log('录像', '30 秒动作录像已保存（静音）')
    except Exception as exc:
        recording = {'state': 'error', 'message': str(exc)}


@app.post('/sim/record')
async def record():
    global recording
    if recording['state'] in ('starting', 'recording', 'saving'):
        raise HTTPException(409, '录像正在进行')
    recording = {'state': 'starting'}
    asyncio.create_task(record_stage())
    return recording


@app.get('/sim')
async def panel():
    return FileResponse(HERE / 'index.html')


@app.get('/stage')
async def stage():
    return FileResponse(WORK / 'stage.html')


@app.get('/')
@app.get('/overlay')
async def avatar():
    return FileResponse(WORK / 'index.html')


app.mount('/static', StaticFiles(directory=WORK), name='static')
app.mount('/recordings', StaticFiles(directory=OUTPUT), name='recordings')
PORT = 17874
if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')

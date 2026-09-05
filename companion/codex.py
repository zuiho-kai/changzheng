"""A single local app-server, independent background task conversations."""
import asyncio
import json
import shutil
import subprocess
import threading
import time


class CodexBridge:
    def __init__(self, store, emit):
        self.store, self.emit = store, emit
        self.proc = None
        self.seq = 0
        self.pending = {}
        self.threads = {}
        self.runs = {}
        self.active_turns = {}
        self.approvals = {}
        self.pause_requested = set()
        self.start_lock = asyncio.Lock()
        self.write_lock = threading.Lock()

    async def start(self):
        async with self.start_lock:
            if self.proc and self.proc.poll() is None:
                return
            binary = shutil.which('codex.exe') or shutil.which('codex')
            if not binary:
                raise RuntimeError('未找到 Codex，请安装并登录 Codex CLI 后重试')
            self.loop = asyncio.get_running_loop()
            self.proc = subprocess.Popen([binary, 'app-server', '--stdio'], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            proc = self.proc
            threading.Thread(target=self._reader, args=(proc,), daemon=True).start()
            await self.call('initialize', {'clientInfo': {'name': 'changzheng_companion', 'version': '0.1.0'}})
            self.send({'method': 'initialized', 'params': {}})

    def _reader(self, proc):
        for line in proc.stdout:
            try:
                value = json.loads(line)
                self.loop.call_soon_threadsafe(self._received, value)
            except (ValueError, RuntimeError):
                pass
        try:
            self.loop.call_soon_threadsafe(self._disconnected, proc)
        except RuntimeError:
            pass

    def _disconnected(self, proc):
        if self.proc is not proc:
            return
        for future in list(self.pending.values()):
            if not future.done():
                future.set_exception(RuntimeError('Codex 连接中断，任务可从历史记录继续'))
        affected = set(self.active_turns)
        for ident, run in list(self.runs.items()):
            if not run.done():
                run.cancel()
                affected.add(ident)
        self.active_turns.clear()
        self.approvals.clear()
        self.pause_requested.difference_update(affected)
        for ident in affected:
            task = self.store.update_task(ident, status='paused', summary='Codex 连接中断，可继续任务')
            asyncio.create_task(self.emit({'type': 'task_updated', 'task': task}))
        self.proc = None

    def send(self, value):
        if not self.proc or self.proc.poll() is not None:
            raise RuntimeError('Codex 未连接')
        with self.write_lock:
            self.proc.stdin.write(json.dumps(value, ensure_ascii=False) + '\n')
            self.proc.stdin.flush()

    async def call(self, method, params, timeout=90):
        self.seq += 1
        ident = self.seq
        future = self.loop.create_future()
        self.pending[ident] = future
        self.send({'id': ident, 'method': method, 'params': params})
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(ident, None)

    def _received(self, value):
        if 'id' in value and 'method' not in value:
            future = self.pending.get(value['id'])
            if future and not future.done():
                if value.get('error'):
                    future.set_exception(RuntimeError(str(value['error'].get('message', 'Codex 请求失败'))[:400]))
                else:
                    future.set_result(value.get('result', {}))
            return
        asyncio.create_task(self._event(value))

    async def _event(self, value):
        method, params = value.get('method', ''), value.get('params', {})
        thread_id = params.get('threadId')
        task_id = self.threads.get(thread_id)
        if 'id' in value:
            if method in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
                self.approvals[str(value['id'])] = value['id']
                await self.emit({'type': 'approval', 'request_id': str(value['id']), 'task_id': task_id,
                    'method': method, 'reason': params.get('reason', ''), 'command': params.get('command', '')})
            else:
                self.send({'id': value['id'], 'error': {'code': -32601,
                    'message': 'This local companion does not support this interactive request yet'}})
            return
        if not task_id:
            return
        if method == 'turn/started':
            self.active_turns[task_id] = params['turn']['id']
        if method == 'item/started':
            kind = params.get('item', {}).get('type')
            label = {'commandExecution': '正在执行命令', 'fileChange': '正在修改文件',
                'mcpToolCall': '正在调用工具', 'webSearch': '正在检索资料'}.get(kind)
            if label:
                await self.emit({'type': 'task_progress', 'task_id': task_id, 'text': label})
        if method == 'item/completed' and params.get('item', {}).get('type') == 'agentMessage':
            text = params['item'].get('text', '')
            if text:
                self.store.update_task(task_id, summary=text[-18000:])
                await self.emit({'type': 'task_progress', 'task_id': task_id, 'text': text})
        if method == 'turn/completed':
            turn = params['turn']
            status = {'completed': 'completed', 'interrupted': 'paused', 'failed': 'failed'}.get(turn['status'], turn['status'])
            fields = {'status': status}
            if turn.get('error'):
                fields['summary'] = str(turn['error'].get('message', '任务失败'))[:1200]
            task = self.store.update_task(task_id, **fields)
            self.active_turns.pop(task_id, None)
            self.pause_requested.discard(task_id)
            await self.emit({'type': 'task_updated', 'task': task})

    async def launch(self, prompt, cwd, task_id=None, read_only=False):
        if task_id:
            task = next((x for x in self.store.tasks() if x['id'] == task_id), None)
            if not task:
                raise ValueError('任务不存在')
            if task_id in self.active_turns or (task_id in self.runs and not self.runs[task_id].done()):
                raise ValueError('任务仍在运行')
            task = self.store.update_task(task_id, status='queued')
        else:
            task = self.store.create_task(prompt, cwd)
            task_id = task['id']
            self.store.set_setting('task_read_only:' + task_id, read_only)
        read_only = self.store.get_setting('task_read_only:' + task_id, read_only)
        self.runs[task_id] = asyncio.create_task(self._run(task_id, prompt, cwd, read_only))
        return task

    async def _run(self, task_id, prompt, cwd, read_only):
        try:
            await self.start()
            task = next(x for x in self.store.tasks() if x['id'] == task_id)
            if task.get('thread_id'):
                thread = await self.call('thread/resume', {'threadId': task['thread_id']})
            else:
                thread = await self.call('thread/start', {'cwd': cwd,
                    'approvalPolicy': 'never' if read_only else 'on-request',
                    'sandbox': 'read-only' if read_only else 'workspace-write',
                    'developerInstructions': '你是本地个人助手的后台执行器。完成用户任务，结果简洁明确并说明验证。不要启动子代理，不要自动发布或向他人发送消息。不要访问无关私密文件。用户打断口头交流不等于取消你的任务。'})
            tid = thread['thread']['id']
            self.threads[tid] = task_id
            if task_id in self.pause_requested:
                task = self.store.update_task(task_id, thread_id=tid, status='paused')
                self.pause_requested.discard(task_id)
                await self.emit({'type': 'task_updated', 'task': task})
                return
            self.store.update_task(task_id, thread_id=tid, status='running')
            await self.emit({'type': 'task_updated', 'task': next(x for x in self.store.tasks() if x['id'] == task_id)})
            reply = await self.call('turn/start', {'threadId': tid, 'effort': 'low',
                'input': [{'type': 'text', 'text': prompt}]})
            current = next(x for x in self.store.tasks() if x['id'] == task_id)
            if current['status'] in ('running', 'pausing'):
                self.active_turns[task_id] = reply['turn']['id']
                if task_id in self.pause_requested:
                    await self.call('turn/interrupt', {'threadId': tid, 'turnId': reply['turn']['id']})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.pause_requested.discard(task_id)
            task = self.store.update_task(task_id, status='failed', summary=str(exc)[:800])
            await self.emit({'type': 'task_updated', 'task': task})

    async def pause(self, task_id):
        task = next((x for x in self.store.tasks() if x['id'] == task_id), None)
        if not task:
            raise ValueError('任务不存在')
        turn_id = self.active_turns.get(task_id)
        if turn_id:
            await self.call('turn/interrupt', {'threadId': task['thread_id'], 'turnId': turn_id})
        elif task_id in self.runs and not self.runs[task_id].done():
            # A sent turn/start may already be executing remotely. Keep awaiting
            # its ID so we can actually interrupt it, rather than cancel only RPC.
            self.pause_requested.add(task_id)
            task = self.store.update_task(task_id, status='pausing')
            await self.emit({'type': 'task_updated', 'task': task})
        return next(x for x in self.store.tasks() if x['id'] == task_id)

    async def approve(self, request_id, accepted):
        ident = self.approvals.pop(request_id, None)
        if ident is None:
            raise ValueError('审批已失效')
        self.send({'id': ident, 'result': {'decision': 'accept' if accepted else 'decline'}})

    async def close(self):
        for task_id in list(self.active_turns):
            try:
                await self.pause(task_id)
            except Exception:
                pass
        for run in self.runs.values():
            if not run.done():
                run.cancel()
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                await asyncio.to_thread(self.proc.wait, 5)
            except subprocess.TimeoutExpired:
                self.proc.terminate()

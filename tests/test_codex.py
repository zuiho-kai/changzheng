import asyncio
from companion.codex import CodexBridge
from companion.store import Store


class DelayedBridge(CodexBridge):
    def __init__(self, store, emit):
        super().__init__(store,emit)
        self.calls=[]
        self.started=asyncio.Event()
        self.release=asyncio.Event()
    async def start(self): pass
    async def call(self, method, params, timeout=90):
        self.calls.append(method)
        if method in ('thread/start','thread/resume'):
            return {'thread':{'id':'test-thread'}}
        if method=='turn/start':
            self.started.set()
            await self.release.wait()
            return {'turn':{'id':'test-turn'}}
        return {}


def test_pause_after_remote_start_sent_waits_for_id_then_interrupts():
    async def run():
        async def emit(event): pass
        store=Store(':memory:'); bridge=DelayedBridge(store,emit)
        task=await bridge.launch('read fixture','.',read_only=True)
        await bridge.started.wait()
        assert (await bridge.pause(task['id']))['status']=='pausing'
        bridge.release.set()
        await bridge.runs[task['id']]
        assert bridge.calls[-1]=='turn/interrupt'
        await bridge._event({'method':'turn/completed','params':{'threadId':'test-thread','turn':{'id':'test-turn','status':'interrupted'}}})
        assert store.tasks()[0]['status']=='paused'
        assert not bridge.active_turns
    asyncio.run(run())


def test_disconnect_during_pause_does_not_poison_resume():
    async def run():
        async def emit(event): pass
        store=Store(':memory:'); bridge=DelayedBridge(store,emit)
        task=await bridge.launch('read fixture','.',read_only=True)
        await bridge.started.wait()
        await bridge.pause(task['id'])
        proc=object(); bridge.proc=proc
        bridge._disconnected(proc)
        await asyncio.gather(bridge.runs[task['id']],return_exceptions=True)
        assert task['id'] not in bridge.pause_requested
        bridge.release.set()
        await bridge.launch('resume','.',task_id=task['id'])
        await bridge.runs[task['id']]
        assert bridge.calls[-1]=='turn/start'
        assert store.tasks()[0]['status']=='running'
    asyncio.run(run())


def test_rpc_failure_clears_pause_before_retry():
    async def run():
        async def emit(event): pass
        class FailingBridge(DelayedBridge):
            fail=True
            async def call(self,method,params,timeout=90):
                result=await super().call(method,params,timeout)
                if method=='turn/start' and self.fail: raise RuntimeError('synthetic failure')
                return result
        store=Store(':memory:'); bridge=FailingBridge(store,emit)
        task=await bridge.launch('read fixture','.',read_only=True)
        await bridge.started.wait(); await bridge.pause(task['id'])
        bridge.release.set(); await bridge.runs[task['id']]
        assert store.tasks()[0]['status']=='failed'
        assert task['id'] not in bridge.pause_requested
        bridge.fail=False
        await bridge.launch('retry','.',task_id=task['id']); await bridge.runs[task['id']]
        assert bridge.calls[-1]=='turn/start'
    asyncio.run(run())

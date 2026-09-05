import asyncio
import time
from companion.runtime import Runtime
from companion.store import Store


class Provider:
    def __init__(self): self.inputs=[]
    async def chat(self,messages,**kwargs):
        self.inputs.append((messages,kwargs))
        yield {'content':'后台检查完成。没有发现错误。'}


async def until(predicate):
    for _ in range(160):
        if predicate(): return
        await asyncio.sleep(.01)
    assert predicate()


def test_private_idle_notice_delivered_only_after_playback_and_no_tool_recursion():
    async def run():
        store=Store(':memory:'); store.set_setting('audio_enabled',False)
        task=store.create_task('检查日志','.')
        completed=store.update_task(task['id'],status='completed',summary='没有发现错误')
        second=store.create_task('第二项任务','.')
        store.update_task(second['id'],status='completed',summary='另一个结果')
        events=[]
        async def emit(event):events.append(event)
        provider=Provider(); rt=Runtime(store,provider,emit)
        rt.controller_present=True; rt.last_activity=time.monotonic()-3
        rt.input_activity(True); await rt.start()
        await asyncio.sleep(.5); assert not provider.inputs
        rt.input_activity(False); rt.last_activity=time.monotonic()-3
        await until(lambda:bool(rt.ledger.pending))
        assert rt.notices.peek('work',True)
        assert provider.inputs[0][1]['tools'] is None
        assert [i for i,m in enumerate(provider.inputs[0][0]) if m['role']=='system']==[0]
        assert '没有发现错误' in str(provider.inputs[0][0])
        for segment in list(rt.ledger.pending):await rt.ack(rt.ledger.turn_id,segment['id'])
        await until(lambda:not rt.ledger.turn_id)
        remaining=rt.notices.peek('work',True)
        assert len(remaining)==1 and remaining[0]['id']==second['id']
        await rt.close()
    asyncio.run(run())


def test_interrupted_notice_stays_pending_but_does_not_repeat_and_live_is_quiet():
    async def run():
        store=Store(':memory:'); store.set_setting('audio_enabled',False)
        task=store.create_task('检查日志','.')
        store.update_task(task['id'],status='completed')
        async def emit(event):pass
        provider=Provider(); rt=Runtime(store,provider,emit)
        rt.controller_present=True
        await rt.new_session('live'); rt.last_activity=time.monotonic()-3; await rt.start()
        await asyncio.sleep(.5); assert not provider.inputs
        await rt.new_session('work'); rt.last_activity=time.monotonic()-3
        await until(lambda:bool(rt.ledger.pending)); await rt.interrupt()
        assert rt.notices.peek('work',True)
        count=len(provider.inputs); rt.last_activity=time.monotonic()-3
        await asyncio.sleep(.5); assert len(provider.inputs)==count
        await rt.close()
    asyncio.run(run())


def test_long_live_reply_is_capped_and_upstream_generator_closed():
    async def run():
        closed=[]
        class LongProvider:
            async def chat(self,*args,**kwargs):
                try:
                    for _ in range(100):yield {'content':'这是一个非常长的直播回答，需要避免一直说下去。'}
                finally:closed.append(True)
        store=Store(':memory:'); store.set_setting('audio_enabled',False)
        async def emit(e):
            if e['type']=='segment':await rt.ack(e['turn_id'],e['id'])
        rt=Runtime(store,LongProvider(),emit); await rt.new_session('live')
        await rt.message('聊聊天',voice=False,source='live')
        await until(lambda: bool(closed))
        await until(lambda:not rt.ledger.turn_id)
        answer=next(x['content'] for x in store.history(rt.session_id) if x['role']=='assistant')
        assert len(answer)<=48 and rt.metrics['speech_budget_reached']
        await rt.close()
    asyncio.run(run())

import asyncio
from companion.inbox import LiveInbox
from companion.runtime import Runtime
from companion.store import Store


def test_flood_is_bounded_latest_unique_and_expires():
    now=[0]
    box=LiveInbox(capacity=100,ttl=15,clock=lambda:now[0])
    for i in range(1000): box.add(str(i),f'话题{i}')
    assert len(box.items)==100
    batch=box.take()
    assert len(batch)==8 and batch[-1]['text']=='话题999'
    assert not box.items
    box.add('甲','你好'); box.add('乙','你好')
    assert box.take()[0]['count']==2
    box.add('甲','过期话题'); now[0]=16
    assert not box.take()


def test_live_arrivals_do_not_interrupt_current_speech():
    async def run():
        class Provider:
            def __init__(self): self.calls=[]; self.tools=[]
            async def chat(self,messages,**kwargs):
                self.calls.append(messages)
                self.tools.append(kwargs.get('tools'))
                yield {'content':'我正在回答。'}
        events=[]
        async def emit(event): events.append(event)
        store=Store(':memory:'); store.set_setting('audio_enabled',False)
        provider=Provider(); rt=Runtime(store,provider,emit)
        rt.controller_present=True
        await rt.new_session('live')
        for i in range(100): await rt.live_message('观众',f'话题{i}')
        await asyncio.sleep(.9)
        tid=rt.ledger.turn_id
        assert tid and len(provider.calls)==1
        for i in range(100): await rt.live_message('观众',f'新话题{i}')
        await asyncio.sleep(.6)
        assert rt.ledger.turn_id==tid and len(provider.calls)==1
        for segment in list(rt.ledger.pending): await rt.ack(tid,segment['id'])
        await asyncio.sleep(1)
        assert len(provider.calls)==2
        assert '"text": "话题' not in str(provider.calls[-1])
        assert all(x is None for x in provider.tools)
        await rt.close()
    asyncio.run(run())


def test_live_inbox_waits_for_player_instead_of_generating_unplayed_speech():
    async def run():
        class Provider:
            async def chat(self, *args, **kwargs):
                raise AssertionError('No model request is allowed without a player')
                yield
        store = Store(':memory:')
        async def emit(event): pass
        runtime = Runtime(store, Provider(), emit)
        try:
            await runtime.new_session('live')
            await runtime.live_message('观众', '听得到吗')
            await asyncio.sleep(.7)
            assert runtime.generation is None and runtime.ledger.turn_id is None
            assert len(runtime.inbox.items) == 1
        finally:
            await runtime.close()
            store.close()
    asyncio.run(run())

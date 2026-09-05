import asyncio
import base64
from companion.runtime import Runtime
from companion.store import Store


class FakeProvider:
    def __init__(self):
        self.inputs = []

    async def chat(self, messages, **kwargs):
        self.inputs.append(messages)
        yield {'content': '先检查日志。再重启服务。'}

    async def json_reply(self, *args, **kwargs):
        return {'memories': []}

    async def speech(self, text, **kwargs):
        return b'test audio', 1


async def wait_for(predicate):
    for _ in range(150):
        if predicate():
            return
        await asyncio.sleep(.01)
    assert predicate(), 'event not received'


def test_actual_next_model_input_excludes_unplayed_suffix():
    async def run():
        events = []
        async def emit(value): events.append(value)
        store = Store(':memory:')
        provider = FakeProvider()
        rt = Runtime(store, provider, emit)
        await rt.message('帮我看看服务', voice=True)
        await wait_for(lambda: any(x['type']=='segment' for x in events))
        first = next(x for x in events if x['type']=='segment')
        await rt.ack(first['turn_id'], first['id'])
        await rt.interrupt()
        assert '再重启' not in str(store.history(rt.session_id))
        await rt.message('先不要重启', voice=False)
        await wait_for(lambda: len(provider.inputs)==2)
        assert '再重启服务' not in str(provider.inputs[-1])
        assert '先检查日志' in str(provider.inputs[-1])
        await rt.close()
    asyncio.run(run())


def test_local_burst_merges_into_one_generation_without_losing_constraints():
    async def run():
        async def emit(value): pass
        provider = FakeProvider()
        rt = Runtime(Store(':memory:'), provider, emit)
        await rt.message('帮我看项目', voice=False)
        await rt.message('只看语音', voice=False)
        await rt.message('不要修改文件', voice=False)
        await wait_for(lambda: bool(provider.inputs))
        assert len(provider.inputs)==1
        assert all(t in str(provider.inputs[0]) for t in ('帮我看项目','只看语音','不要修改文件'))
        await rt.close()
    asyncio.run(run())


def test_old_ack_cannot_pollute_a_new_generation():
    async def run():
        events=[]
        async def emit(value): events.append(value)
        rt=Runtime(Store(':memory:'),FakeProvider(),emit)
        await rt.message('第一件事', voice=True)
        await wait_for(lambda:any(x['type']=='segment' for x in events))
        old=next(x for x in events if x['type']=='segment')
        await rt.message('换个话题', voice=True)
        await rt.ack(old['turn_id'],old['id'])
        assert not any(x['role']=='assistant' for x in rt.store.history(rt.session_id))
        await rt.close()
    asyncio.run(run())

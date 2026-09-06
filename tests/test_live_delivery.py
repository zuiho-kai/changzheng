import asyncio

from companion.runtime import Runtime
from companion.speech import DeliveryPrefix
from companion.store import Store


def test_expression_prefix_is_removed_even_when_split_across_network_chunks():
    parser=DeliveryPrefix()
    text=''.join(parser.feed(x) for x in [' [ha','ppy',']哎，','这句我可听见了！'])
    assert parser.expression=='happy'
    assert text=='哎，这句我可听见了！'


def test_plain_reply_is_not_lost_and_unknown_english_tag_is_not_spoken():
    parser=DeliveryPrefix()
    assert parser.feed('今天')+parser.feed('聊什么？')=='今天聊什么？'
    parser=DeliveryPrefix()
    assert parser.feed('[unknown]我在。')=='我在。'
    assert parser.expression=='neutral'


def test_live_expression_drives_speech_but_only_played_words_enter_history():
    async def run():
        calls=[];events=[]
        class Provider:
            async def chat(self, *args, **kwargs):
                for text in ['[cur','ious]哪', '里怪了？']:
                    yield {'content':text}
            async def speech(self,text,**kwargs):
                calls.append((text,kwargs))
                return b'audio',1
        async def emit(event): events.append(event)
        store=Store(':memory:');runtime=Runtime(store,Provider(),emit)
        await runtime.new_session('live')
        await runtime.message('有点怪感觉',voice=True,source='live')
        for _ in range(80):
            if any(e['type']=='segment' for e in events):break
            await asyncio.sleep(.01)
        segment=next(e for e in events if e['type']=='segment')
        assert calls==[('哪里怪了？',{'voice':'claire','style':'curious'})]
        expression=next(e for e in events if e['type']=='avatar_performance')
        assert expression['turn_id']==segment['turn_id'] and expression['expression']=='curious'
        assert not any(m['role']=='assistant' for m in store.history(runtime.session_id))
        await runtime.ack(segment['turn_id'],segment['id'])
        for _ in range(40):
            if not runtime.ledger.turn_id:break
            await asyncio.sleep(.01)
        answer=[m['content'] for m in store.history(runtime.session_id) if m['role']=='assistant']
        assert answer==['哪里怪了？']
        await runtime.close();store.close()
    asyncio.run(run())

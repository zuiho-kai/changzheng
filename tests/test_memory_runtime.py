import asyncio
from companion.runtime import Runtime
from companion.store import Store


async def until(predicate):
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(.01)
    assert predicate()


async def emit(event):
    pass


def test_shutdown_restarts_unfinished_extraction_and_forget_never_resurrects(tmp_path):
    async def run():
        entered = asyncio.Event()
        class Slow:
            async def json_reply(self, messages):
                entered.set()
                await asyncio.Event().wait()
        store = Store(tmp_path / 'memory.db')
        rt = Runtime(store, Slow(), emit)
        msg = store.add_message(rt.session_id, 'user', '我工作时喜欢无糖绿茶', scene='work')
        rt.memory_jobs.enqueue(msg['id'], 'work')
        await rt.start()
        await entered.wait()
        await rt.close()
        assert rt.memory_jobs.list_jobs()[0]['status'] == 'pending'
        assert rt.memory_jobs.list_jobs()[0]['attempts'] == 0
        store.close()

        class Good:
            async def json_reply(self, messages):
                return {'memories': [{'content': '用户工作时喜欢无糖绿茶', 'scene': 'work'}]}
        store = Store(tmp_path / 'memory.db')
        rt = Runtime(store, Good(), emit)
        await rt.start()
        await until(lambda: rt.memory_jobs.list_jobs()[0]['status'] == 'done')
        assert len(store.memories()) == 1
        memory = store.memories()[0]
        store.forget_memory(memory['id'])
        await rt.invalidate_memory()
        assert not rt.memory_jobs.enqueue(msg['id'], 'work')
        await asyncio.sleep(.55)
        assert store.memories() == []
        await rt.close()
        store.close()
    asyncio.run(run())


def test_failed_extraction_retries_without_holding_conversation_and_setting_pauses():
    async def run():
        calls = []
        class Flaky:
            async def json_reply(self, messages):
                calls.append(messages)
                if len(calls) == 1:
                    raise RuntimeError('provider unavailable')
                return {'memories': []}
        store = Store(':memory:')
        store.set_setting('auto_memory', False)
        rt = Runtime(store, Flaky(), emit)
        msg = store.add_message(rt.session_id, 'user', '我的偏好需要长期记住', scene='chat')
        rt.memory_jobs.enqueue(msg['id'], 'chat')
        rt.memory_jobs.base_delay = .01
        await rt.start()
        await asyncio.sleep(.55)
        assert not calls
        store.set_setting('auto_memory', True)
        await until(lambda: rt.memory_jobs.list_jobs()[0]['status'] == 'done')
        assert len(calls) == 2
        assert rt.memory_jobs.list_jobs()[0]['attempts'] == 2
        await rt.close()
    asyncio.run(run())


def test_memory_edit_stops_reclaim_until_old_source_is_excluded():
    async def run():
        entered = asyncio.Event()
        calls = []
        class Provider:
            async def json_reply(self, messages):
                calls.append(1)
                entered.set()
                if len(calls) == 1:
                    await asyncio.Event().wait()
                return {'memories': [{'content': '用户最喜欢咖啡'}]}
        store = Store(':memory:')
        rt = Runtime(store, Provider(), emit)
        msg = store.add_message(rt.session_id, 'user', '我喜欢咖啡', scene='chat')
        memory = store.add_memory('用户喜欢咖啡', source_id=msg['id'])
        rt.memory_jobs.enqueue(msg['id'], 'chat')
        await rt.start()
        await entered.wait()
        await rt.invalidate_memory()
        await asyncio.sleep(.05)  # Even a caller delay cannot reclaim old input.
        assert len(calls) == 1
        store.update_memory(memory['id'], '用户喜欢茶')
        rt.resume_memory()
        await asyncio.sleep(.55)
        assert [m['content'] for m in store.memories()] == ['用户喜欢茶']
        assert rt.memory_jobs.list_jobs()[0]['status'] == 'canceled'
        await rt.close()
    asyncio.run(run())


def test_switching_off_during_request_preserves_pending_without_writing():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        class Provider:
            async def json_reply(self, messages):
                entered.set()
                await release.wait()
                return {'memories': [{'content': '用户喜欢咖啡'}]}
        store = Store(':memory:')
        rt = Runtime(store, Provider(), emit)
        msg = store.add_message(rt.session_id, 'user', '我喜欢咖啡', scene='chat')
        rt.memory_jobs.enqueue(msg['id'], 'chat')
        await rt.start()
        await entered.wait()
        store.set_setting('auto_memory', False)
        release.set()
        await until(lambda: rt.memory_jobs.list_jobs()[0]['status'] == 'pending')
        assert not store.memories()
        await rt.close()
    asyncio.run(run())


def test_automatic_correction_during_speech_cannot_reinsert_old_context():
    async def run():
        store = Store(':memory:')
        entered, release = asyncio.Event(), asyncio.Event()
        captured = []
        class Provider:
            async def chat(self, messages, **kwargs):
                captured.extend(messages)
                entered.set()
                await release.wait()
                yield {'content': '你喜欢咖啡。'}
        async def played(event):
            if event['type'] == 'segment':
                await rt.ack(event['turn_id'], event['id'])
        rt = Runtime(store, Provider(), played)
        rt.voice = False
        original = store.add_message(rt.session_id, 'user', '我喜欢咖啡')
        memory = store.add_memory('用户喜欢咖啡', source_id=original['id'])
        generation = asyncio.create_task(rt._generate())
        await entered.wait()
        tid = rt.ledger.turn_id
        assert '用户喜欢咖啡' in str(captured)
        changed = store.add_message(rt.session_id, 'user', '现在不再喝咖啡，改喝茶')
        store.reconcile_memory(memory, '用户现在改喝茶', changed['id'], supersede=True)
        release.set()
        await generation
        assert all(m['role'] != 'assistant' for m in store.history(rt.session_id))
        # Playback truth is preserved as an audit row, excluded from model input.
        row = store._rows('SELECT content,excluded FROM messages WHERE id=?', (tid,))[0]
        assert row == {'content': '你喜欢咖啡。', 'excluded': 1}
        assert '你喜欢咖啡。' not in str(rt.context())
        await rt.close()
    asyncio.run(run())

"""Real extraction and semantic reconciliation using only synthetic owner facts."""
import asyncio
import json
from pathlib import Path
import time
from companion.providers import Provider
from companion.runtime import Runtime
from companion.store import Store

ROOT = Path(__file__).resolve().parents[1]


async def main():
    folder = ROOT / 'artifacts' / ('runtime-reconcile-' + str(time.time_ns()))
    folder.mkdir()
    store = Store(folder / 'memory.db')
    report = {'checks': {}, 'stages': []}
    class AuditedProvider(Provider):
        async def json_reply(self, messages, **kwargs):
            result = await super().json_reply(messages, **kwargs)
            if 'same|supersede|new' in messages[0]['content']:
                report.setdefault('decisions', []).append(result)
            return result
    provider = AuditedProvider()
    async def emit(event): pass
    rt = Runtime(store, provider, emit)
    await rt.new_session('work')
    await rt.start()
    async def learn(text):
        message = store.add_message(rt.session_id, 'user', text, scene='work')
        rt.memory_jobs.enqueue(message['id'], 'work')
        for _ in range(500):
            jobs = {j['message_id']: j for j in rt.memory_jobs.list_jobs()}
            if jobs[message['id']]['status'] in ('done', 'failed', 'canceled'):
                break
            await asyncio.sleep(.1)
        assert jobs[message['id']]['status'] == 'done', jobs[message['id']]
        report['stages'].append([{'content': m['content'], 'scene': m['scene']} for m in store.memories()])
        return message
    try:
        first = await learn('请记住，我工作时喜欢喝无糖咖啡。')
        second = await learn('我干活时偏好喝不加糖的咖啡。')
        memories = store.memories()
        report['checks']['synonyms_share_one_canonical_memory'] = len(memories) == 1
        sources = store._rows('SELECT source_id FROM memory_sources')
        report['checks']['both_original_sources_preserved'] = {s['source_id'] for s in sources} == {first['id'], second['id']}
        store.add_message(rt.session_id, 'assistant', '你工作时喜欢无糖咖啡。', scene='work', source='played')
        await learn('从现在起，我工作时不再喝咖啡，改喝无糖绿茶。请按新的偏好记住。')
        current = store.memories()
        report['checks']['explicit_change_replaces_old_preference'] = len(current) == 1 and '绿茶' in current[0]['content']
        active = store.history(rt.session_id)
        report['checks']['old_source_and_assistant_removed_from_context'] = not any(m['id'] in (first['id'], second['id']) or m['role'] == 'assistant' for m in active)
        recall = await rt.memory_search.recall('干活困了喝点什么', 'work')
        report['checks']['current_preference_recalled'] = any('绿茶' in m['content'] for m in recall)
        report['checks']['private_preference_not_in_live'] = not await rt.memory_search.recall('干活困了喝点什么', 'live')
        await rt.invalidate_memory()
        for memory in store.memories():
            store.forget_memory(memory['id'])
        rt.resume_memory()
        await asyncio.sleep(.6)
        report['checks']['forget_excludes_all_associated_sources'] = not store.memories() and not store.history(rt.session_id)
    finally:
        await rt.close()
        await provider.close()
        store.close()
    (ROOT / 'artifacts/memory-reconciliation-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert all(report['checks'].values())


if __name__ == '__main__':
    asyncio.run(main())

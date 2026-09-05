import json

import pytest

from companion.memory_jobs import MemoryJobs
from companion.store import Store


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / 'memory.db')
    now = [100.0]
    jobs = MemoryJobs(store, clock=lambda: now[0])
    session = store.new_session()
    yield store, jobs, session, now
    store.close()


def source(store, session, **kwargs):
    return store.add_message(session, kwargs.pop('role', 'user'),
                             '我喜欢安静的咖啡馆。', **kwargs)['id']


def test_restart_recovers_inflight_request(tmp_path):
    path = tmp_path / 'restart.db'
    store = Store(path)
    sid = source(store, store.new_session())
    jobs = MemoryJobs(store)
    assert jobs.enqueue(sid, 'chat')
    assert jobs.claim()['attempts'] == 1
    store.close()
    restarted = Store(path)
    try:
        jobs = MemoryJobs(restarted)
        recovered = jobs.claim()
        assert recovered['id'] == recovered['message_id'] == recovered['source_id'] == sid
        assert recovered['content'] == '我喜欢安静的咖啡馆。'
        assert recovered['attempts'] == 2
        assert jobs.complete(sid)
        assert jobs.claim() is None
    finally:
        restarted.close()


def test_enqueue_and_claim_are_idempotent(setup):
    store, jobs, session, _ = setup
    sid = source(store, session)
    assert jobs.enqueue(sid, 'chat')
    assert not jobs.enqueue(sid, 'chat')
    assert jobs.claim()['message_id'] == sid
    assert jobs.claim() is None
    assert jobs.complete(sid)
    assert not jobs.complete(sid)
    assert not jobs.enqueue(sid, 'chat')
    assert len(jobs.list_jobs()) == 1


def test_explicit_retry_only_requeues_failed_valid_sources(setup):
    store, jobs, session, now = setup
    sid = source(store, session)
    jobs.enqueue(sid, 'chat')
    for _ in range(3):
        assert jobs.claim()
        jobs.retry(sid, RuntimeError('private provider body'))
        now[0] += 100
    assert jobs.list_jobs()[0]['status'] == 'failed'
    assert jobs.retry_failed() == 1
    assert jobs.claim()['attempts'] == 1
    with store.conn:
        store.conn.execute('UPDATE messages SET excluded=1 WHERE id=?', (sid,))
    jobs.retry(sid, RuntimeError('failure'))
    assert jobs.retry_failed() == 0
    assert jobs.list_jobs()[0]['status'] == 'canceled'


@pytest.mark.parametrize('invalidate', ['exclude', 'delete', 'forget'])
def test_source_invalidation_prevents_recreation(setup, invalidate):
    store, jobs, session, _ = setup
    sid = source(store, session)
    jobs.enqueue(sid, 'chat')
    jobs.claim()
    if invalidate == 'forget':
        memory = store.add_memory('喜欢安静的咖啡馆', source_id=sid)
        store.forget_memory(memory['id'])
    else:
        with store._lock, store.conn:
            statement = ('DELETE FROM messages WHERE id=?' if invalidate == 'delete'
                         else 'UPDATE messages SET excluded=1 WHERE id=?')
            store.conn.execute(statement, (sid,))
    assert not jobs.retry(sid, 'network failed')
    assert not jobs.complete(sid)
    assert not jobs.enqueue(sid, 'chat')
    assert MemoryJobs(store).claim() is None
    assert jobs.list_jobs()[0]['status'] == 'canceled'


def test_bounded_retries_and_clock_backoff(setup):
    store, jobs, session, now = setup
    sid = source(store, session)
    jobs.enqueue(sid, 'chat')
    for attempt, delay in [(1, 5), (2, 10), (3, 20)]:
        assert jobs.claim()['attempts'] == attempt
        assert jobs.retry(sid, TimeoutError('private provider body'))
        assert jobs.claim() is None
        now[0] += delay - .1
        assert jobs.claim() is None
        now[0] += .1
    assert jobs.claim() is None
    assert not jobs.enqueue(sid, 'chat')
    assert jobs.list_jobs()[0]['status'] == 'failed'
    assert MemoryJobs(store, clock=lambda: now[0]).claim() is None


@pytest.mark.parametrize('kwargs', [dict(role='assistant'), dict(role='tool'),
    dict(source='live'), dict(source='tool')])
def test_only_local_owner_messages_are_eligible(setup, kwargs):
    store, jobs, session, _ = setup
    sid = source(store, session, **kwargs)
    assert not jobs.enqueue(sid, kwargs.get('scene', 'chat'))
    assert jobs.list_jobs() == []


def test_local_owner_is_eligible_in_live_scene(setup):
    store, jobs, session, _ = setup
    sid = source(store, session, scene='live')
    assert jobs.enqueue(sid, 'live')
    assert jobs.claim()['scene'] == 'live'


def test_scene_cannot_be_relabelled_and_inspection_has_no_private_text(setup):
    store, jobs, session, _ = setup
    sid = source(store, session, scene='work')
    assert not jobs.enqueue(sid, 'live')
    assert not jobs.enqueue(sid, 'chat')
    assert jobs.enqueue(sid, 'work')
    assert jobs.claim()['scene'] == 'work'
    jobs.retry(sid, 'sk-synthetic-secret; private provider body')
    encoded = json.dumps(jobs.list_jobs(), ensure_ascii=False)
    assert 'sk-synthetic' not in encoded
    assert '咖啡馆' not in encoded
    assert 'private provider body' not in encoded


def test_crashes_are_bounded_too(setup):
    store, jobs, session, now = setup
    sid = source(store, session)
    jobs.enqueue(sid, 'chat')
    for attempt in range(1, 4):
        assert jobs.claim()['attempts'] == attempt
        jobs = MemoryJobs(store, clock=lambda: now[0])
    assert jobs.claim() is None
    assert jobs.list_jobs()[0]['status'] == 'failed'

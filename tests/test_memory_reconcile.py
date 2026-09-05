import asyncio
import json

import pytest

from companion.memory_reconcile import MemoryReconciler
from companion.store import Store


class Judge:
    def __init__(self, decision, during=None):
        self.decision, self.during, self.inputs = decision, during, []

    async def json_reply(self, messages):
        self.inputs.append(json.loads(messages[-1]['content']))
        if self.during:
            self.during()
        return self.decision


@pytest.fixture
def db(tmp_path):
    store = Store(tmp_path / 'memory.db')
    yield store, store.new_session()
    store.close()


def say(db, text, scene='chat'):
    return db[0].add_message(db[1], 'user', text, scene=scene)['id']


def remember(db, judge, text, source, scene='all', source_scene='chat'):
    return asyncio.run(MemoryReconciler(db[0], judge).remember(
        {'content': text, 'scene': scene, 'kind': 'preference'}, source, source_scene))


def verdict(memory, action='same', **extra):
    return {'action': action, 'id': memory['id'], 'confidence': .98, **extra}


def test_synonyms_share_canonical_and_forget_all_sources(db):
    store, session = db
    first = say(db, '我喜欢安静的咖啡馆')
    old = store.add_memory('用户喜欢安静的咖啡馆', source_id=first)
    second = say(db, '我偏爱不吵闹的咖啡店')
    result = remember(db, Judge(verdict(old)), '用户偏爱不吵闹的咖啡店', second)
    assert result['id'] == old['id']
    assert result['content'] == old['content']
    store.forget_memory(old['id'])
    assert store.history(session) == []
    for source in (first, second):
        with pytest.raises(ValueError, match='source'):
            store.add_memory('咖啡馆', source_id=source)


def test_explicit_correction_replaces_old_context_and_latest_provenance(db):
    store, session = db
    first = say(db, '我喜欢喝咖啡')
    old = store.add_memory('用户喜欢喝咖啡', source_id=first)
    store.add_message(session, 'assistant', '你喜欢咖啡')
    text = '我现在不再喝咖啡，改喝茶了'
    second = say(db, text)
    judge = Judge(verdict(old, 'supersede', explicit_change=True, evidence=text))
    result = remember(db, judge, '用户现在喜欢喝茶', second)
    assert result['id'] == old['id']
    assert result['source_id'] == second and result['source_text'] == text
    assert [m['content'] for m in store.history(session)] == [text]
    assert store.recall('咖啡') == []
    assert store.recall('喝茶')[0]['id'] == old['id']
    assert len(store._rows('SELECT * FROM memory_sources')) == 2
    store.forget_memory(old['id'])
    assert store.history(session) == []


@pytest.mark.parametrize('text,evidence', [('我以前喜欢咖啡', '我以前喜欢咖啡'),
    ('我也喜欢喝茶', '我也喜欢喝茶'), ('我以前改喝咖啡', '我以前改喝咖啡'),
    ('我现在喜欢喝茶', '伪造的不再喝咖啡')])
def test_historical_or_ordinary_preferences_cannot_supersede(db, text, evidence):
    store, _ = db
    old = store.add_memory('用户现在喜欢牛奶', source_id=say(db, '我现在喜欢牛奶'))
    judge = Judge(verdict(old, 'supersede', explicit_change=True, evidence=evidence))
    new = remember(db, judge, '用户以前喜欢咖啡', say(db, text))
    assert new['id'] != old['id']
    assert store._one('memories', old['id'])['content'] == old['content']


def test_candidate_scene_privacy_and_source_snapshot_are_filtered(db):
    store, _ = db
    store.add_memory('私人咖啡喜好', scene='all', visibility='private')
    store.add_memory('工作咖啡喜好', scene='work', visibility='public')
    old = store.add_memory('公开咖啡喜好', scene='all', visibility='public',
                           source_id=say(db, '公开咖啡喜好，秘密源文本'))
    judge = Judge(verdict(old))
    remember(db, judge, '公开咖啡偏好', say(db, '公开咖啡偏好', 'live'), source_scene='live')
    assert judge.inputs[0]['candidates'] == [{'id': old['id'], 'content': old['content']}]
    assert '秘密源文本' not in json.dumps(judge.inputs, ensure_ascii=False)


@pytest.mark.parametrize('action', ['same', 'supersede'])
@pytest.mark.parametrize('mutation', ['edit', 'delete', 'exclude_source'])
def test_stale_candidate_or_invalid_source_cannot_write(db, action, mutation):
    store, _ = db
    old = store.add_memory('用户喜欢咖啡', source_id=say(db, '我喜欢咖啡'))
    text = '我现在不再喝咖啡，改喝茶'
    source = say(db, text)
    def change():
        if mutation == 'edit':
            store.update_memory(old['id'], '用户喜欢牛奶')
        elif mutation == 'delete':
            store.forget_memory(old['id'])
        else:
            with store.conn:
                store.conn.execute('UPDATE messages SET excluded=1 WHERE id=?', (source,))
    judge = Judge(verdict(old, action, explicit_change=True, evidence=text), change)
    with pytest.raises(ValueError):
        remember(db, judge, '用户喜欢喝茶', source)
    assert not any(m['content'] == '用户喜欢喝茶' for m in store.memories())


def test_older_queued_source_cannot_overwrite_newer_preference(db):
    store, _ = db
    source = say(db, '我现在不再喝咖啡，改喝茶')
    old = store.add_memory('用户喜欢牛奶', source_id=say(db, '我现在改喝牛奶'))
    judge = Judge(verdict(old, 'supersede', explicit_change=True, evidence='改喝茶'))
    with pytest.raises(ValueError, match='newer'):
        remember(db, judge, '用户喜欢喝茶', source)


@pytest.mark.parametrize('decision', [{'action': 'same', 'id': 'invented', 'confidence': 1},
    {'action': 'same', 'confidence': .5}, {'action': 'same', 'confidence': True}])
def test_low_confidence_and_unprovided_ids_create_new_fact(db, decision):
    old = db[0].add_memory('用户喜欢咖啡')
    decision.setdefault('id', old['id'])
    new = remember(db, Judge(decision), '用户喜欢茶', say(db, '我喜欢茶'))
    assert new['id'] != old['id']


def test_candidate_count_is_bounded(db):
    for i in range(40):
        db[0].add_memory(f'用户偏好第{i}种饮料')
    judge = Judge({'action': 'new'})
    remember(db, judge, '用户喜欢茶', say(db, '我喜欢茶'))
    assert len(judge.inputs[0]['candidates']) == 30

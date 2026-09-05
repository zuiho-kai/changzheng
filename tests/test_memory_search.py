import asyncio
import pytest
from companion.store import Store
from companion.memory import MemorySearch


class Embeddings:
    def __init__(self): self.calls = []
    async def embed(self, texts):
        self.calls.append(texts)
        return [[1.,0.] if any(word in t for word in ('咖啡','提神','茶')) else [0.,1.] for t in texts]


def test_semantic_recall_persists_filters_and_forgets(tmp_path):
    async def run():
        path=tmp_path/'memory.db'
        store=Store(path)
        fact=store.add_memory('用户偏爱咖啡', scene='work')
        store.add_memory('用户喜欢猫', scene='chat', visibility='public')
        provider=Embeddings()
        search=MemorySearch(store,provider)
        assert not store.recall('我该喝什么提神',scene='work')
        assert [m['id'] for m in await search.recall('我该喝什么提神','work')]==[fact['id']]
        store.close()
        store=Store(path)
        provider=Embeddings()
        search=MemorySearch(store,provider)
        assert await search.recall('我该喝什么提神','work')
        assert provider.calls==[['我该喝什么提神']]
        assert not await search.recall('咖啡','live')
        store.update_memory(fact['id'],'用户偏爱茶')
        result=await search.recall('喝什么提神','work')
        assert result[0]['content']=='用户偏爱茶'
        store.forget_memory(fact['id'])
        assert not await search.recall('喝什么提神','work')
        assert not store._rows('SELECT * FROM memory_vectors')
        store.close()
    asyncio.run(run())


def test_duplicate_correction_is_controlled():
    store=Store(':memory:')
    first=store.add_memory('喜欢咖啡')
    store.add_memory('喜欢茶')
    with pytest.raises(ValueError, match='已有相同'):
        store.update_memory(first['id'],'喜欢茶')
    assert len(store.memories())==2

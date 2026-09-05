import asyncio
from companion import app
from companion.runtime import Runtime
from companion.store import Store


def test_failed_owner_send_cleans_turn_without_recursive_control_deadlock(monkeypatch):
    async def run():
        class Dead:
            async def send_json(self, event):
                raise RuntimeError('closed')
        ws = Dead()
        store = Store(':memory:')
        rt = Runtime(store, object(), app.emit)
        rt.controller_present = True
        rt.ledger.begin()
        rt.ledger.stage('尚未播放的内容')
        monkeypatch.setattr(app, 'runtime', rt)
        monkeypatch.setattr(app, 'CLIENTS', {ws: 'control'})
        monkeypatch.setattr(app, 'OWNER', ws)
        async with rt.control:
            await app.emit({'type': 'status', 'status': 'speaking'})
            assert app.OWNER is None and not rt.controller_present
        for _ in range(50):
            if not rt.ledger.turn_id:
                break
            await asyncio.sleep(.01)
        assert not rt.ledger.turn_id
        assert not store.history(rt.session_id)
        await rt.close()
    asyncio.run(run())

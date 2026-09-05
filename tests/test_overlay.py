import asyncio
from types import SimpleNamespace
import companion.app as module


def test_overlay_does_not_receive_private_scene_text():
    async def run():
        events=[]
        class Socket:
            async def send_json(self,event): events.append(event)
        socket=Socket()
        old_clients, old_runtime=module.CLIENTS,module.runtime
        try:
            module.CLIENTS={socket:'observer'}
            module.runtime=SimpleNamespace(scene='chat',settings=lambda:{'avatar':''})
            await module.emit({'type':'segment_committed','heard':'private secret'})
            await module.emit({'type':'turn_finished','heard':'private secret'})
            await module.emit({'type':'mouth','turn_id':'private-turn','value':.8})
            assert not events
            await module.emit({'type':'state','history':['private'],'memories':['private']})
            assert 'private' not in str(events)
            module.runtime.scene='live'
            await module.emit({'type':'segment_committed','heard':'public hello'})
            assert events[-1]['heard']=='public hello'
            await module.emit({'type':'mouth','turn_id':'live-turn','value':.8})
            assert events[-1]['value']==.8
        finally:
            module.CLIENTS, module.runtime=old_clients,old_runtime
    asyncio.run(run())

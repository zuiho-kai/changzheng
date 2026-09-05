import asyncio
from types import SimpleNamespace

from fastapi import WebSocketDisconnect
from companion import app


def test_mouth_requires_current_turn_and_finite_numeric_value(monkeypatch):
    async def run():
        events=[]
        async def emit(event): events.append(event)
        async def interrupt(): pass
        rt=SimpleNamespace(ledger=SimpleNamespace(turn_id='current'), interrupt=interrupt,
                           state=lambda: {}, scene='live')
        class Socket:
            headers={'host':'127.0.0.1:17867','origin':'http://127.0.0.1:17867'}
            query_params={}
            async def accept(self): pass
            async def send_json(self, event): pass
            async def receive_json(self):
                try: return next(self.messages)
                except StopIteration: raise WebSocketDisconnect()
        ws=Socket()
        ws.messages=iter([
            {'type':'mouth','turn_id':turn,'value':value}
            for turn,value in [('stale',.9),(None,.9),('current',float('nan')),
                               ('current',float('inf')),('current',True),('current',-.1),
                               ('current',1.1),('current','0.5'),('current',.6),('current',0)]])
        monkeypatch.setattr(app,'runtime',rt)
        monkeypatch.setattr(app,'OWNER',None)
        monkeypatch.setattr(app,'CLIENTS',{})
        monkeypatch.setattr(app,'emit',emit)
        await app.socket(ws)
        assert [e['value'] for e in events]==[.6,0]
    asyncio.run(run())

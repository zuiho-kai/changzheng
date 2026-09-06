import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

pytest.importorskip('blivedm')  # Optional live-platform dependency.
from companion.bilibili import Client, Relay
from blivedm.clients.ws_base import HeaderTuple, Operation
import aiohttp


def message(text='你好', **kwargs):
    return SimpleNamespace(msg=text, timestamp=1000, rnd=17, uid=kwargs.get('uid', 1),
                           uid_crc32=str(kwargs.get('uid', 1)), uname='观众')


def test_event_dedup_keeps_same_text_from_different_viewers_and_expires():
    now = [0]
    relay = Relay('http://127.0.0.1:17870', clock=lambda: now[0])
    relay.receive(6, message()); relay.receive(6, message())
    relay.receive(6, message(uid=2))
    assert relay.queue.qsize() == 2 and relay.stats['duplicates'] == 1
    now[0] = 61
    relay.receive(6, message())
    assert relay.queue.qsize() == 3
    for i in range(150):
        relay.receive(6, message(str(i)))
    assert relay.queue.qsize() == 100 and relay.stats['overflow'] == 53


def test_forward_only_live_and_fresh_no_retry_after_ambiguous_post():
    async def run():
        now, scene, requests = [0], ['chat'], []
        def endpoint(request):
            requests.append(request)
            if request.method == 'GET':
                return httpx.Response(200, json={'scene': scene[0]})
            if scene[0] == 'error':
                raise httpx.ReadTimeout('ambiguous POST', request=request)
            return httpx.Response(200, json={'buffered': 1})
        relay = Relay('http://127.0.0.1:17870', clock=lambda: now[0])
        async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as http:
            entry = (0, {'user': '观众', 'text': '测试'})
            await relay.forward_one(http, entry)
            assert relay.stats['inactive'] == 1 and len(requests) == 1
            scene[0] = 'live'
            await relay.forward_one(http, entry)
            assert relay.stats['forwarded'] == 1
            assert json.loads(requests[-1].content)['text'] == '测试'
            now[0] = 16
            await relay.forward_one(http, entry)
            assert relay.stats['expired'] == 1 and len(requests) == 3
            def timeout_post(request):
                requests.append(request)
                if request.method == 'GET':
                    return httpx.Response(200, json={'scene': 'live'})
                raise httpx.ReadTimeout('ambiguous', request=request)
            async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_post)) as failing:
                await relay.forward_one(failing, (16, entry[1]))
            assert relay.stats['forward_errors'] == 1 and len(requests) == 5
    asyncio.run(run())


def test_listen_only_never_buffers_for_ai():
    relay = Relay('http://127.0.0.1:17870', listen_only=True)
    relay.receive(6, message())
    assert relay.stats['received'] == 1 and relay.queue.empty()


def test_auth_state_requires_server_acceptance_and_heartbeat():
    async def run():
        relay = Relay('http://127.0.0.1:17870')
        async with aiohttp.ClientSession() as session:
            client = Client(6, relay, session=session)
            packets = []
            class Socket:
                async def send_bytes(self, data): packets.append(data)
            client._websocket = Socket()
            header = HeaderTuple(0, 16, 1, Operation.AUTH_REPLY, 1)
            await client._parse_business_message(header, b'{"code":0}')
            assert relay.stats['state'] == 'authenticated' and packets
            client._handle_command({'cmd':'_HEARTBEAT', 'data':{'popularity':1}})
            assert relay.stats['state'] == 'connected' and relay.stats['heartbeats'] == 1
            await client._on_ws_close()
            assert relay.stats['state'] == 'disconnected'
            assert client._get_reconnect_interval(100, 100) == 30
            await client.close()
    asyncio.run(run())

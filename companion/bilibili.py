"""Bilibili web danmaku -> existing local live inbox, in a separate process."""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import blivedm
import httpx
from blivedm.clients.ws_base import Operation
from yarl import URL


class Relay:
    def __init__(self, target, listen_only=False, clock=time.monotonic):
        self.target = target.rstrip('/')
        self.listen_only, self.clock = listen_only, clock
        self.queue = asyncio.Queue(maxsize=100)
        self.seen = OrderedDict()
        self.stats = dict(state='starting', received=0, duplicates=0, expired=0,
                          overflow=0, forwarded=0, inactive=0, forward_errors=0,
                          heartbeats=0, reconnects=0, last_message=None, messages=[])

    def receive(self, room_id, message):
        self.stats['received'] += 1
        text = message.msg.strip()[:300]
        if not text:
            return
        now = self.clock()
        # Include event time/rnd and sender identity: identical text from separate
        # viewers remains separate input so LiveInbox can count repeated topics.
        raw = [room_id, message.timestamp, message.rnd, message.uid,
               message.uid_crc32, message.uname, text]
        key = hashlib.sha256(json.dumps(raw, ensure_ascii=False).encode()).hexdigest()
        while self.seen and now - next(iter(self.seen.values())) > 60:
            self.seen.popitem(last=False)
        if key in self.seen:
            self.stats['duplicates'] += 1
            return
        self.seen[key] = now
        if len(self.seen) > 4096:
            self.seen.popitem(last=False)
        self.stats['last_message'] = {'text': text, 'event_id': key, 'at': time.time()}
        self.stats['messages'] = (self.stats['messages'] + [
            {'user': message.uname or '观众', 'text': text, 'event_id': key, 'at': time.time()}
        ])[-8:]
        if self.listen_only:
            return
        if self.queue.full():
            self.queue.get_nowait()
            self.stats['overflow'] += 1
        self.queue.put_nowait((now, {'user': message.uname or '观众', 'text': text}))

    async def forward_one(self, http, entry):
        created, payload = entry
        if self.clock() - created > 15:
            self.stats['expired'] += 1
            return
        try:
            # Never switch a private conversation into live mode automatically.
            state = await http.get(self.target + '/api/state')
            state.raise_for_status()
            if state.json()['scene'] != 'live':
                self.stats['inactive'] += 1
                return
            if self.clock() - created > 15:
                self.stats['expired'] += 1
                return
            response = await http.post(self.target + '/api/live/messages', json=payload)
            if response.status_code == 400:
                self.stats['inactive'] += 1
                return
            response.raise_for_status()
            self.stats['forwarded'] += 1
        except (httpx.HTTPError, ValueError, KeyError):
            # Do not retry an ambiguous POST: it might already be in the inbox.
            self.stats['forward_errors'] += 1

    async def forward(self):
        async with httpx.AsyncClient(timeout=3, trust_env=False) as http:
            while True:
                await self.forward_one(http, await self.queue.get())


class Handler(blivedm.BaseHandler):
    def __init__(self, relay):
        self.relay = relay

    def _on_danmaku(self, client, message):
        if not message.is_mirror:
            self.relay.receive(client.room_id, message)

    def _on_heartbeat(self, client, message):
        self.relay.stats.update(state='connected', last_heartbeat=time.time())
        self.relay.stats['heartbeats'] += 1

    def on_client_stopped(self, client, exception):
        if exception:
            self.relay.stats.update(state='failed', error=type(exception).__name__)


class Client(blivedm.BLiveClient):
    def __init__(self, room_id, relay, **kwargs):
        self.relay = relay
        super().__init__(room_id, **kwargs)
        self.set_handler(Handler(relay))
        self.set_reconnect_policy(lambda retry, total: min(30, 2 ** min(retry, 5)))

    async def _on_before_ws_connect(self, retry_count):
        self.relay.stats['state'] = 'connecting'
        if retry_count:
            self.relay.stats['reconnects'] += 1
        await super()._on_before_ws_connect(retry_count)
        self.relay.stats['room_id'] = self.room_id

    async def _parse_business_message(self, header, body):
        await super()._parse_business_message(header, body)
        if header.operation == Operation.AUTH_REPLY:
            self.relay.stats.update(state='authenticated', authenticated_at=time.time())

    async def _on_ws_close(self):
        await super()._on_ws_close()
        self.relay.stats['state'] = 'disconnected'


async def run(args):
    # Upstream debug/error logs can contain full server replies. Persist only
    # selected counters and exception types; never credentials or auth tokens.
    logging.getLogger('blivedm').setLevel(logging.CRITICAL)
    relay = Relay(args.target, args.listen_only)
    relay.stats.update(requested_room=args.room, listen_only=args.listen_only)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    def snapshot():
        relay.stats['updated_at'] = time.time()
        temporary = report.with_suffix('.tmp')
        try:
            temporary.write_text(json.dumps(relay.stats, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(report)
            relay.stats.pop('report_error', None)
        except OSError as error:
            # Windows readers may briefly deny replacement. A status-file race
            # must never terminate the active danmaku connection.
            relay.stats['report_error'] = type(error).__name__
    worker = asyncio.create_task(relay.forward())
    deadline = time.monotonic() + args.seconds if args.seconds else float('inf')
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12), trust_env=True) as session:
            # Optional locally supplied login. No browser-profile extraction.
            if os.environ.get('BILIBILI_SESSDATA'):
                session.cookie_jar.update_cookies({'SESSDATA': os.environ['BILIBILI_SESSDATA']},
                                                  response_url=URL('https://www.bilibili.com/'))
            while time.monotonic() < deadline:
                client = Client(args.room, relay, session=session)
                client.start()
                try:
                    while client.is_running and time.monotonic() < deadline:
                        socket = client._websocket
                        heartbeat = relay.stats.get('last_heartbeat', 0)
                        closed = socket is not None and socket.closed
                        stale = relay.stats['state'] == 'connected' and time.time() - heartbeat > 65
                        if closed or stale:
                            relay.stats.update(state='reconnecting', last_disconnect_reason='socket_closed' if closed else 'heartbeat_timeout')
                            break
                        snapshot()
                        await asyncio.sleep(min(1, max(0, deadline-time.monotonic())))
                finally:
                    await client.stop_and_close()
                if time.monotonic() < deadline:
                    # Initialization errors terminate upstream's network task;
                    # the supervisor retries them as well as ordinary WS drops.
                    relay.stats['reconnects'] += 1
                    snapshot()
                    await asyncio.sleep(min(10, max(0, deadline-time.monotonic())))
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        relay.stats['state_before_stop'] = relay.stats['state']
        relay.stats['state'] = 'stopped'
        snapshot()
        print(json.dumps(relay.stats, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--room', type=int, required=True)
    parser.add_argument('--target', default='http://127.0.0.1:17870')
    parser.add_argument('--listen-only', action='store_true', help='Observe without sending to the local AI')
    parser.add_argument('--seconds', type=float, default=0, help='0 = run until interrupted')
    parser.add_argument('--report', default='artifacts/runtime-bilibili/status.json')
    args = parser.parse_args()
    target = urlparse(args.target)
    if args.room <= 0 or args.seconds < 0:
        parser.error('room must be positive; seconds must be nonnegative')
    if target.scheme != 'http' or target.hostname not in ('127.0.0.1', 'localhost', '::1'):
        parser.error('target must be a local HTTP companion instance')
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

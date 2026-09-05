"""Lossy live attention, never a FIFO response backlog."""
import time
from collections import deque


class LiveInbox:
    def __init__(self, capacity=100, ttl=15, clock=time.monotonic):
        self.items = deque(maxlen=capacity)
        self.ttl, self.clock = ttl, clock
        self.received = 0
        self.dropped = 0

    def add(self, user, text):
        self.received += 1
        if len(self.items) == self.items.maxlen:
            self.dropped += 1
        self.items.append((self.clock(), str(user)[:40], str(text).strip()[:300]))

    def take(self, limit=8):
        now, recent = self.clock(), []
        while self.items:
            entry = self.items.popleft()
            if now-entry[0] <= self.ttl and entry[2]:
                recent.append(entry)
            else:
                self.dropped += 1
        # Latest unique topics win. Repeated identical chat becomes a count.
        groups = {}
        for order, (timestamp, user, text) in enumerate(recent):
            if text in groups:
                groups[text]['count'] += 1
                groups[text]['user'] = user
                groups[text]['at'] = timestamp
                groups[text]['order'] = order
            else:
                groups[text] = {'text': text, 'user': user, 'count': 1, 'at': timestamp, 'order': order}
        selected = sorted(groups.values(), key=lambda x:x['order'], reverse=True)[:limit]
        self.dropped += max(0, len(groups)-limit)
        return list(reversed(selected))

    def clear(self):
        self.items.clear()

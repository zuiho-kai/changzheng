"""Persistent, private completion notices; delivery is explicitly acknowledged.

Task summaries remain data. The caller owns presentation, playback, and deciding
whether a completed playback or explicit user action qualifies as delivery.
"""

from threading import RLock


class TaskNotices:
    SETTING = 'task_completion_notices_v1'

    def __init__(self, store):
        self.store = store
        self._lock = RLock()
        saved = store.get_setting(self.SETTING, {})
        self._pending = {self._key(row): dict(row) for row in saved.get('pending', [])}
        self._acknowledged = {tuple(key) for key in saved.get('acknowledged', [])}
        self._latest = dict(saved.get('latest', {}))
        # Recover completion events missed during process shutdown/disconnection.
        for task in reversed(store.tasks()):
            self.observe(task)

    @staticmethod
    def _key(task):
        return str(task['id']), str(task['updated_at'])

    def _save(self):
        self.store.set_setting(self.SETTING, {
            'pending': list(self._pending.values()),
            'acknowledged': sorted(self._acknowledged),
            'latest': self._latest,
        })

    def observe(self, task):
        """Queue a previously unseen completed/failed task version."""
        if not task.get('id') or not task.get('updated_at'):
            return False
        key = self._key(task)
        with self._lock:
            previous = self._latest.get(key[0], '')
            if key[1] < previous:
                return False
            self._latest[key[0]] = key[1]
            stale = [k for k in self._pending if k[0] == key[0] and
                (k != key or task.get('status') not in ('completed', 'failed'))]
            for old in stale:
                del self._pending[old]
            if task.get('status') not in ('completed', 'failed'):
                if stale or previous != key[1]:
                    self._save()
                return False
            if key in self._pending or key in self._acknowledged:
                if stale:
                    self._save()
                return False
            self._pending[key] = {
                'id': key[0], 'updated_at': key[1], 'status': task['status'],
                'prompt': str(task.get('prompt', '')),
                'summary': str(task.get('summary', '')),
            }
            self._save()
            return True

    def peek(self, scene, idle):
        """Return at most three notices without marking any as delivered.

        The caller must pass idle=False during owner input, generation, playback,
        or another active notice. Live and unknown scenes never expose notices.
        """
        if scene not in ('chat', 'work') or not idle:
            return []
        with self._lock:
            # Refresh against durable current state if an event was missed.
            for task in self.store.tasks():
                self.observe(task)
            return [dict(row) for row in list(self._pending.values())[:3]]

    def acknowledge(self, tasks):
        """Acknowledge exact id/updated_at versions after confirmed delivery."""
        count = 0
        with self._lock:
            for task in tasks:
                if not task.get('id') or not task.get('updated_at'):
                    continue
                key = self._key(task)
                if key not in self._pending:
                    continue
                del self._pending[key]
                self._acknowledged.add(key)
                count += 1
            if count:
                self._save()
        return count

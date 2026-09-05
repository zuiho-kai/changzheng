"""Durable local extraction requests; a worker supplies all model/network work."""

import time


class MemoryJobs:
    MAX_ATTEMPTS = 3
    _VALID_SOURCE = """EXISTS (SELECT 1 FROM messages m WHERE m.id=memory_jobs.message_id
        AND m.excluded=0 AND m.role='user' AND m.source='user')"""

    def __init__(self, store, *, clock=time.time, base_delay=5, max_delay=60):
        self.store, self.clock = store, clock
        self.base_delay, self.max_delay = max(0, base_delay), max(0, max_delay)
        with store._lock, store.conn:
            store.conn.execute('''CREATE TABLE IF NOT EXISTS memory_jobs (
                message_id TEXT PRIMARY KEY, scene TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                available_at REAL NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                error TEXT NOT NULL DEFAULT '')''')
            # Construct once per application worker lifetime, after its predecessor stopped.
            store.conn.execute('''UPDATE memory_jobs SET
                status=CASE WHEN attempts<? THEN 'pending' ELSE 'failed' END,
                available_at=?,updated_at=? WHERE status='processing' ''',
                (self.MAX_ATTEMPTS, clock(), clock()))
            self._invalidate()

    def _invalidate(self):
        self.store.conn.execute(f'''UPDATE memory_jobs SET status='canceled',updated_at=?,error=''
            WHERE status IN ('pending','processing','failed') AND NOT {self._VALID_SOURCE}''',
            (self.clock(),))

    def enqueue(self, message_id, scene):
        """Persist one eligible source once; done/failed/canceled jobs never resurrect."""
        now = self.clock()
        with self.store._lock, self.store.conn:
            source = self.store.conn.execute('''SELECT scene FROM messages WHERE id=?
                AND excluded=0 AND role='user' AND source='user' ''',
                (message_id,)).fetchone()
            if source is None or source['scene'] != scene:
                return False
            cursor = self.store.conn.execute('''INSERT OR IGNORE INTO memory_jobs
                (message_id,scene,available_at,created_at,updated_at) VALUES (?,?,?,?,?)''',
                (message_id, scene, now, now, now))
            return cursor.rowcount == 1

    def claim(self):
        """Atomically claim the oldest due source, reading its current content locally."""
        with self.store._lock, self.store.conn:
            self.store.conn.execute('BEGIN IMMEDIATE')
            self._invalidate()
            row = self.store.conn.execute('''SELECT j.*,m.content FROM memory_jobs j
                JOIN messages m ON m.id=j.message_id WHERE j.status='pending'
                AND j.available_at<=? AND j.attempts<? ORDER BY j.created_at,j.rowid LIMIT 1''',
                (self.clock(), self.MAX_ATTEMPTS)).fetchone()
            if row is None:
                return None
            self.store.conn.execute('''UPDATE memory_jobs SET status='processing',
                attempts=attempts+1,updated_at=? WHERE message_id=?''',
                (self.clock(), row['message_id']))
            result = dict(row)
            result.update(id=row['message_id'], source_id=row['message_id'],
                          status='processing', attempts=row['attempts'] + 1)
            return result

    def complete(self, message_id):
        with self.store._lock, self.store.conn:
            self._invalidate()
            cursor = self.store.conn.execute('''UPDATE memory_jobs SET status='done',
                updated_at=?,error='' WHERE message_id=? AND status='processing' ''',
                (self.clock(), message_id))
            return cursor.rowcount == 1

    def retry(self, message_id, error):
        """Bound retries without storing provider error bodies, prompts, or credentials."""
        with self.store._lock, self.store.conn:
            self._invalidate()
            row = self.store.conn.execute('''SELECT attempts FROM memory_jobs
                WHERE message_id=? AND status='processing' ''', (message_id,)).fetchone()
            if row is None:
                return False
            delay = min(self.max_delay, self.base_delay * 2 ** (row['attempts'] - 1))
            status = 'failed' if row['attempts'] >= self.MAX_ATTEMPTS else 'pending'
            category = type(error).__name__ if isinstance(error, Exception) else 'extraction_failed'
            self.store.conn.execute('''UPDATE memory_jobs SET status=?,available_at=?,
                updated_at=?,error=? WHERE message_id=?''',
                (status, self.clock() + delay, self.clock(), category, message_id))
            return True

    def release(self, message_id):
        """A local cancellation is not a failed model attempt."""
        with self.store._lock, self.store.conn:
            self._invalidate()
            self.store.conn.execute('''UPDATE memory_jobs SET status='pending',
                attempts=MAX(0,attempts-1),available_at=?,updated_at=?
                WHERE message_id=? AND status='processing' ''',
                (self.clock(), self.clock(), message_id))

    def cancel_pending(self):
        """Cancel invalidated sources only, preserving unrelated unfinished work."""
        with self.store._lock, self.store.conn:
            self._invalidate()

    def list_jobs(self):
        """Inspectable job metadata only; source text is returned solely by claim()."""
        with self.store._lock, self.store.conn:
            self._invalidate()
            return [dict(row) for row in self.store.conn.execute(
                'SELECT * FROM memory_jobs ORDER BY created_at,rowid')]

    def retry_failed(self):
        """Explicit owner retry; canceled/invalid sources stay excluded."""
        with self.store._lock, self.store.conn:
            self._invalidate()
            cursor = self.store.conn.execute('''UPDATE memory_jobs SET status='pending',
                attempts=0,available_at=?,updated_at=?,error='' WHERE status='failed' ''',
                (self.clock(), self.clock()))
            return cursor.rowcount

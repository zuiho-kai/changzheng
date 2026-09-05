"""Local SQLite history and explicit, scene-scoped long-term memory.

Assistant messages supplied here must contain only confirmed played/heard text.
Source snapshots are kept for the memory editor, never used as recall content.
"""

import json
import math
import re
import sqlite3
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now():
    return datetime.now(timezone.utc).isoformat()


def _normal(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def _terms(text):
    normalized = _normal(text)
    terms = set(re.findall(r'[a-z0-9_]+', normalized))
    # Chinese has no whitespace boundaries; bigrams preserve useful concepts
    # without matching every unrelated sentence on a common single character.
    for run in re.findall(r'[\u3400-\u9fff]+', normalized):
        terms.update(run[i:i + 2] for i in range(len(run) - 1))
        if len(run) == 1:
            terms.add(run)
    return terms


class Store:
    def __init__(self, path):
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, scene TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
                role TEXT NOT NULL, content TEXT NOT NULL, scene TEXT NOT NULL,
                source TEXT NOT NULL, created_at TEXT NOT NULL, excluded INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id);
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, content TEXT NOT NULL, normalized TEXT NOT NULL,
                scene TEXT NOT NULL, visibility TEXT NOT NULL, source_id TEXT,
                source_text TEXT, kind TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, UNIQUE(normalized, scene, visibility)
            );
            CREATE TABLE IF NOT EXISTS memory_sources (
                memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL, PRIMARY KEY(memory_id, source_id)
            );
            INSERT OR IGNORE INTO memory_sources (memory_id, source_id)
                SELECT id, source_id FROM memories WHERE source_id IS NOT NULL;
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, prompt TEXT NOT NULL, cwd TEXT NOT NULL,
                thread_id TEXT, status TEXT NOT NULL, summary TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
        ''')

    def _rows(self, sql, args=()):
        with self._lock:
            return [dict(row) for row in self.conn.execute(sql, args).fetchall()]

    def _one(self, table, item_id):
        rows = self._rows(f'SELECT * FROM {table} WHERE id=?', (item_id,))
        if not rows:
            raise KeyError(item_id)
        row = rows[0]
        row.pop('normalized', None)
        row.pop('excluded', None)
        return row

    def new_session(self, scene='chat'):
        session_id = uuid.uuid4().hex
        with self._lock, self.conn:
            self.conn.execute('INSERT INTO sessions VALUES (?,?,?)', (session_id, scene, _now()))
        return session_id

    def add_message(self, session_id, role, content, *, message_id=None, scene='chat', source='user', context_revision=None):
        if role not in ('user', 'assistant', 'system', 'tool'):
            raise ValueError('Invalid message role')
        message_id = message_id or uuid.uuid4().hex
        with self._lock, self.conn:
            self.conn.execute('BEGIN IMMEDIATE')
            existing = self._rows('SELECT * FROM messages WHERE id=?', (message_id,))
            if existing:
                row = existing[0]
                if (row['session_id'], row['role'], row['content']) != (session_id, role, content):
                    raise ValueError('Message id already belongs to different content')
                return self._one('messages', message_id)
            excluded = role == 'assistant' and context_revision is not None and context_revision != self.get_setting('memory_context_revision', 0)
            self.conn.execute('''INSERT INTO messages
                (id,session_id,role,content,scene,source,created_at,excluded) VALUES (?,?,?,?,?,?,?,?)''',
                (message_id, session_id, role, content, scene, source, _now(), int(excluded)))
            return self._one('messages', message_id)

    def history(self, session_id, limit=24):
        rows = self._rows('''SELECT id,session_id,role,content,scene,source,created_at FROM messages
            WHERE session_id=? AND excluded=0 ORDER BY rowid DESC LIMIT ?''',
            (session_id, max(0, limit)))
        return list(reversed(rows))

    def clear_session(self, session_id):
        with self._lock, self.conn:
            self.conn.execute('DELETE FROM messages WHERE session_id=?', (session_id,))

    def add_memory(self, content, scene='all', visibility='private', source_id=None, kind='fact'):
        normalized = _normal(content)
        if not normalized:
            raise ValueError('Memory cannot be empty')
        if visibility not in ('private', 'public'):
            raise ValueError('Visibility must be private or public')
        with self._lock, self.conn:
            source = self._rows('SELECT content,excluded FROM messages WHERE id=?', (source_id,)) if source_id is not None else []
            if source_id is not None and (not source or source[0]['excluded']):
                raise ValueError('Memory source is missing or excluded from context')
            duplicate = self._rows('SELECT id FROM memories WHERE normalized=? AND scene=? AND visibility=?',
                                   (normalized, scene, visibility))
            if duplicate:
                memory_id = duplicate[0]['id']
                if source:
                    self.conn.execute('''UPDATE memories SET source_id=?,source_text=?
                        WHERE id=? AND source_id IS NULL''', (source_id, source[0]['content'], memory_id))
                    self.conn.execute('INSERT OR IGNORE INTO memory_sources VALUES (?,?)', (memory_id, source_id))
                return self._one('memories', memory_id)
            memory_id, now = uuid.uuid4().hex, _now()
            self.conn.execute('INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?)',
                (memory_id, content.strip(), normalized, scene, visibility, source_id,
                 source[0]['content'] if source else None, kind, now, now))
            if source:
                self.conn.execute('INSERT INTO memory_sources VALUES (?,?)', (memory_id, source_id))
            return self._one('memories', memory_id)

    def memories(self):
        rows = self._rows('SELECT * FROM memories ORDER BY updated_at DESC, rowid DESC')
        for row in rows:
            row.pop('normalized', None)
        return rows

    def reconcile_memory(self, candidate, content, source_id, *, supersede=False, kind=None):
        """Attach a synonym or replace an explicitly changed fact with one atomic CAS."""
        normalized = _normal(content)
        if not normalized:
            raise ValueError('Memory cannot be empty')
        with self._lock, self.conn:
            # Acquire the SQLite write lock before reading the candidate/source,
            # including when a second Store connection edits the same database.
            self.conn.execute('BEGIN IMMEDIATE')
            sources = self._rows('''SELECT rowid AS sequence,* FROM messages WHERE id=?
                AND excluded=0 AND role='user' AND source='user' ''', (source_id,))
            if not sources:
                raise ValueError('Memory source is missing or excluded from context')
            rows = self._rows('SELECT * FROM memories WHERE id=?', (candidate['id'],))
            fields = ('content', 'updated_at', 'scene', 'visibility')
            if not rows or any(rows[0][key] != candidate[key] for key in fields):
                raise ValueError('Memory candidate changed during reconciliation')
            old, source = rows[0], sources[0]
            if supersede:
                newest = self._rows('''SELECT MAX(m.rowid) AS sequence FROM memory_sources s
                    JOIN messages m ON m.id=s.source_id WHERE s.memory_id=?''', (old['id'],))[0]['sequence']
                if newest is not None and source['sequence'] <= newest:
                    raise ValueError('Memory correction source must be newer than existing sources')
                duplicate = self._rows('''SELECT id FROM memories WHERE normalized=?
                    AND scene=? AND visibility=? AND id<>?''',
                    (normalized, old['scene'], old['visibility'], old['id']))
                if duplicate:
                    raise ValueError('Memory correction would duplicate an existing fact')
                self.conn.execute('''UPDATE messages SET excluded=1 WHERE id<>? AND
                    (role='assistant' OR id IN
                    (SELECT source_id FROM memory_sources WHERE memory_id=?))''',
                    (source_id, old['id']))
                self._bump_memory_revision()
                self.conn.execute('''UPDATE memories SET content=?,normalized=?,source_id=?,
                    source_text=?,kind=?,updated_at=? WHERE id=?''',
                    (content.strip(), normalized, source_id, source['content'],
                     kind or old['kind'], _now(), old['id']))
            else:
                # Keep the canonical wording. Even "same" must not recreate an
                # old candidate after a concurrent editor delete/correction.
                self.conn.execute('''UPDATE memories SET source_id=COALESCE(source_id,?),
                    source_text=COALESCE(source_text,?),updated_at=? WHERE id=?''',
                    (source_id, source['content'], _now(), old['id']))
            self.conn.execute('INSERT OR IGNORE INTO memory_sources VALUES (?,?)', (old['id'], source_id))
            return self._one('memories', old['id'])

    def recall(self, query, scene='chat', limit=6):
        query_terms = _terms(query)
        if not query_terms or limit <= 0:
            return []
        sql = "SELECT * FROM memories WHERE scene IN (?, 'all')"
        if scene == 'live':
            sql += " AND visibility='public'"
        candidates = self._rows(sql, (scene,))
        ranked = []
        for row in candidates:
            terms = _terms(row['content'])
            overlap = query_terms & terms
            if not overlap:
                continue
            score = len(overlap) / math.sqrt(max(1, len(terms)))
            # Provenance is editor-only: stale/private source wording must not
            # sneak into the prompt when a corrected/public fact is recalled.
            row.pop('normalized', None)
            row.pop('source_text', None)
            ranked.append((score, row['updated_at'], row))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [row for _, _, row in ranked[:limit]]

    def _invalidate_context(self, memory):
        # A recalled fact may have been repeated in any session. Without a
        # per-generation dependency graph, conservatively hide all assistant
        # history and remove the original source from future model inputs.
        self.conn.execute('''UPDATE messages SET excluded=1 WHERE role='assistant'
            OR id IN (SELECT source_id FROM memory_sources WHERE memory_id=?)''', (memory['id'],))
        self._bump_memory_revision()

    def _bump_memory_revision(self):
        # Caller owns the existing write transaction; do not nest set_setting.
        version = self.get_setting('memory_context_revision', 0) + 1
        self.conn.execute('''INSERT INTO settings VALUES ('memory_context_revision',?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value''', (json.dumps(version),))

    def update_memory(self, memory_id, content, scene=None, visibility=None):
        if not _normal(content):
            raise ValueError('Memory cannot be empty')
        if visibility is not None and visibility not in ('private', 'public'):
            raise ValueError('Visibility must be private or public')
        with self._lock, self.conn:
            old = self._one('memories', memory_id)
            duplicate = self._rows('SELECT id FROM memories WHERE normalized=? AND scene=? AND visibility=? AND id<>?',
                (_normal(content), scene if scene is not None else old['scene'],
                 visibility if visibility is not None else old['visibility'], memory_id))
            if duplicate:
                raise ValueError('已有相同内容、场景和可见性的记忆，可删除重复项')
            self.conn.execute('''UPDATE memories SET content=?,normalized=?,scene=?,visibility=?,updated_at=?
                WHERE id=?''', (content.strip(), _normal(content), scene if scene is not None else old['scene'],
                               visibility if visibility is not None else old['visibility'], _now(), memory_id))
            self._invalidate_context(old)
            return self._one('memories', memory_id)

    def forget_memory(self, memory_id):
        with self._lock, self.conn:
            rows = self._rows('SELECT * FROM memories WHERE id=?', (memory_id,))
            if not rows:
                return
            self._invalidate_context(rows[0])
            self.conn.execute('DELETE FROM memories WHERE id=?', (memory_id,))

    def set_setting(self, key, value):
        with self._lock, self.conn:
            self.conn.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                              (key, json.dumps(value, ensure_ascii=False)))

    def get_setting(self, key, default=None):
        rows = self._rows('SELECT value FROM settings WHERE key=?', (key,))
        return json.loads(rows[0]['value']) if rows else default

    def create_task(self, prompt, cwd, thread_id=None):
        task_id, now = uuid.uuid4().hex, _now()
        with self._lock, self.conn:
            self.conn.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)',
                              (task_id, prompt, str(cwd), thread_id, 'queued', '', now, now))
            return self._one('tasks', task_id)

    def update_task(self, task_id, **fields):
        allowed = {'prompt', 'cwd', 'thread_id', 'status', 'summary'}
        if fields.keys() - allowed:
            raise ValueError('Unsupported task fields')
        with self._lock, self.conn:
            self._one('tasks', task_id)
            fields['updated_at'] = _now()
            columns = ','.join(f'{key}=?' for key in fields)
            self.conn.execute(f'UPDATE tasks SET {columns} WHERE id=?', (*fields.values(), task_id))
            return self._one('tasks', task_id)

    def tasks(self):
        return self._rows('SELECT * FROM tasks ORDER BY created_at DESC, rowid DESC')

    def close(self):
        with self._lock:
            self.conn.close()

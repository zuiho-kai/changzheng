"""Persistent semantic index; scene/privacy filters apply before ranking."""
import hashlib
import json
import math


class MemorySearch:
    def __init__(self, store, provider):
        self.store, self.provider = store, provider
        with store._lock, store.conn:
            store.conn.execute('''CREATE TABLE IF NOT EXISTS memory_vectors (
                memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
                digest TEXT NOT NULL, vector TEXT NOT NULL)''')

    async def recall(self, query, scene='chat', limit=6):
        fallback = self.store.recall(query, scene, limit)
        candidates = [m for m in self.store.memories() if m['scene'] in (scene, 'all')
                      and (scene != 'live' or m['visibility'] == 'public')]
        if not candidates or not query.strip() or not hasattr(self.provider, 'embed'):
            return fallback
        cached = {r['memory_id']: r for r in self.store._rows('SELECT * FROM memory_vectors')}
        missing = []
        for m in candidates:
            digest = hashlib.sha256(m['content'].encode()).hexdigest()
            if m['id'] not in cached or cached[m['id']]['digest'] != digest:
                missing.append((m, digest))
        # Limit first-use indexing work; remaining recent memories are indexed on later queries.
        missing = missing[:24]
        vectors = await self.provider.embed([query] + [m['content'] for m, _ in missing])
        if len(vectors) != len(missing) + 1:
            return fallback
        with self.store._lock, self.store.conn:
            for (m, digest), vector in zip(missing, vectors[1:]):
                # Memory may have been deleted/edited during the network call.
                rows = self.store._rows('SELECT content FROM memories WHERE id=?', (m['id'],))
                if not rows or rows[0]['content'] != m['content']:
                    continue
                encoded = json.dumps(vector)
                self.store.conn.execute('INSERT OR REPLACE INTO memory_vectors VALUES (?,?,?)', (m['id'], digest, encoded))
                cached[m['id']] = {'digest': digest, 'vector': encoded}
        q = vectors[0]
        qnorm = math.sqrt(sum(x*x for x in q)) or 1
        ranked = []
        lexical = {m['id'] for m in fallback}
        # Re-read the filtered candidates so late edits cannot return stale content.
        for m in self.store.memories():
            if m['scene'] not in (scene, 'all') or (scene == 'live' and m['visibility'] != 'public'):
                continue
            record = cached.get(m['id'])
            digest = hashlib.sha256(m['content'].encode()).hexdigest()
            score = 0
            if record and record['digest'] == digest:
                v = json.loads(record['vector'])
                if len(v) == len(q):
                    score = sum(a*b for a,b in zip(q,v)) / (qnorm*(math.sqrt(sum(x*x for x in v)) or 1))
            # Small-model cosine is not a probability. A .50 gate missed real
            # Chinese paraphrases in our fixture (.449); unrelated probes <.40.
            if score >= .43 or m['id'] in lexical:
                m.pop('source_text', None)
                ranked.append((score + (.08 if m['id'] in lexical else 0), m))
        ranked.sort(key=lambda x:x[0], reverse=True)
        return [m for _,m in ranked[:limit]]

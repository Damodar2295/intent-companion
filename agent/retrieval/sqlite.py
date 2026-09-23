"""Local persistent vector/FTS index. Exact cosine scans, not an ANN or enterprise DB."""

import json
import math
import re
import sqlite3
from pathlib import Path
from threading import RLock

from agent.retrieval.contracts import RetrievalHit, VectorRecord
from agent.retrieval.filters import matches


class SQLiteVectorStore:
    def __init__(self, path, embedding_space=None):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = RLock()
        self.embedding_space = embedding_space
        try:
            with self.db:
                self.db.executescript("""
                    CREATE TABLE IF NOT EXISTS retrieval_config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS retrieval_documents (
                        id TEXT PRIMARY KEY, kind TEXT NOT NULL, text TEXT NOT NULL, vector TEXT NOT NULL,
                        metadata TEXT NOT NULL, digest TEXT NOT NULL, version INTEGER NOT NULL,
                        dimensions INTEGER NOT NULL, updated_at TEXT NOT NULL);
                    CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_fts USING fts5(id UNINDEXED, text);
                """)
        except Exception:
            self.db.close()
            raise

    async def fingerprints(self):
        with self.lock:
            return {row["id"]: row["digest"] for row in self.db.execute("SELECT id, digest FROM retrieval_documents")}

    async def upsert(self, records):
        if not records:
            return
        if not self.embedding_space:
            raise ValueError("An explicit embedding space is required for writes")
        dimensions = len(records[0].embedding)
        if len({r.record_id for r in records}) != len(records):
            raise ValueError("Duplicate record IDs in batch")
        if any(
            not r.embedding
            or len(r.embedding) != dimensions
            or any(not math.isfinite(v) for v in r.embedding)
            or not any(r.embedding)
            for r in records
        ):
            raise ValueError("Embeddings must be finite, nonzero and dimensionally consistent")
        # Serialize/validate the whole batch before writing anything.
        payloads = []
        for r in records:
            if r.metadata.get("source_type") != "SYNTHETIC":
                raise ValueError("Local ingestion permits synthetic catalog content only")
            digest = r.metadata.get("content_hash")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Content hash required")
            payloads.append((r, json.dumps(r.embedding, allow_nan=False), json.dumps(r.metadata, allow_nan=False)))
        with self.lock, self.db:
            space = self.db.execute("SELECT value FROM retrieval_config WHERE key='embedding_space'").fetchone()
            expected = json.dumps({"name": self.embedding_space, "dimensions": dimensions}, sort_keys=True)
            if space and space["value"] != expected:
                raise ValueError("Embedding space mismatch; use a separate index for a new model")
            self.db.execute("INSERT OR IGNORE INTO retrieval_config VALUES ('embedding_space', ?)", (expected,))
            for r, vector, metadata in payloads:
                self.db.execute(
                    """
                    INSERT INTO retrieval_documents VALUES (?, ?, ?, ?, ?, ?, 1, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                    ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, text=excluded.text,
                        vector=excluded.vector, metadata=excluded.metadata, digest=excluded.digest,
                        version=retrieval_documents.version+1, dimensions=excluded.dimensions,
                        updated_at=excluded.updated_at WHERE retrieval_documents.digest != excluded.digest
                """,
                    (
                        r.record_id,
                        r.document_type,
                        r.searchable_text,
                        vector,
                        metadata,
                        r.metadata["content_hash"],
                        dimensions,
                    ),
                )
                self.db.execute("DELETE FROM retrieval_fts WHERE id=?", (r.record_id,))
                self.db.execute("INSERT INTO retrieval_fts VALUES (?, ?)", (r.record_id, r.searchable_text))

    async def stats(self):
        with self.lock:
            counts = dict(self.db.execute("SELECT kind, count(*) FROM retrieval_documents GROUP BY kind"))
            space = self.db.execute("SELECT value FROM retrieval_config WHERE key='embedding_space'").fetchone()
            last = self.db.execute("SELECT max(updated_at) FROM retrieval_documents").fetchone()[0]
        return {
            "backend": "sqlite-exact-cosine-fts5",
            "records": sum(counts.values()),
            "by_type": counts,
            "embedding_space": json.loads(space[0]) if space else None,
            "last_updated_at": last,
            "embedding_kind": ("test" if json.loads(space[0])["name"].startswith("test-hash") else "model")
            if space
            else "none",
            "semantic_quality_verified": False,
            "scope": "synthetic-ingestion-only",
        }

    def _record(self, row):
        metadata = json.loads(row["metadata"])
        metadata["document_version"] = row["version"]
        return VectorRecord(row["id"], row["kind"], row["text"], tuple(json.loads(row["vector"])), metadata)

    def _matches(self, row, filters):
        metadata = json.loads(row["metadata"])
        return matches(row["kind"], metadata, filters)

    async def semantic_search(self, embedding, filters, top_k):
        with self.lock:
            space = self.db.execute("SELECT value FROM retrieval_config WHERE key='embedding_space'").fetchone()
            if space:
                configured = json.loads(space[0])
                if self.embedding_space != configured["name"] or len(embedding) != configured["dimensions"]:
                    raise ValueError("Query embedding space or dimension mismatch")
            if not embedding or not any(embedding) or any(not math.isfinite(v) for v in embedding):
                raise ValueError("Query embedding must be finite and nonzero")
            rows = self.db.execute("SELECT * FROM retrieval_documents ORDER BY id").fetchall()
        norm = math.sqrt(sum(v * v for v in embedding))
        hits = []
        for row in rows:
            if self._matches(row, filters):
                record = self._record(row)
                score = sum(a * b for a, b in zip(embedding, record.embedding, strict=True)) / (
                    norm * math.sqrt(sum(v * v for v in record.embedding))
                )
                label = "test_hash_cosine" if self.embedding_space.startswith("test-hash") else "cosine"
                hits.append(RetrievalHit(record, score, label))
        return sorted(hits, key=lambda h: (-h.score, h.record.record_id))[: max(0, min(top_k, 1000))]

    async def lexical_search(self, query, filters, top_k):
        words = re.findall(r"\w+", query)[:64]
        if not words or top_k <= 0:
            return []
        expression = " OR ".join('"' + word + '"' for word in words)
        with self.lock:
            rows = self.db.execute(
                """
                SELECT d.*, bm25(retrieval_fts) AS rank FROM retrieval_fts
                JOIN retrieval_documents d ON d.id=retrieval_fts.id
                WHERE retrieval_fts MATCH ? ORDER BY rank, d.id
            """,
                (expression,),
            ).fetchall()
        return [
            RetrievalHit(self._record(row), -row["rank"], "fts5_bm25") for row in rows if self._matches(row, filters)
        ][: min(top_k, 1000)]

    async def delete(self, record_ids):
        with self.lock, self.db:
            self.db.executemany("DELETE FROM retrieval_fts WHERE id=?", [(key,) for key in record_ids])
            self.db.executemany("DELETE FROM retrieval_documents WHERE id=?", [(key,) for key in record_ids])

    def close(self):
        self.db.close()

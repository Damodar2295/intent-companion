"""Prepare all changed embeddings before one atomic index publish."""

import asyncio

from agent.retrieval.contracts import EmbeddingService, IngestionStore, VectorRecord
from agent.retrieval.documents import SearchDocument


class IngestionUnavailable(Exception):
    pass


class IngestionService:
    def __init__(self, store: IngestionStore, embeddings: EmbeddingService | None, embedding_space: str | None):
        self.store, self.embeddings, self.embedding_space = store, embeddings, embedding_space
        self.lock = asyncio.Lock()

    async def ingest(self, documents: list[SearchDocument]):
        if self.embeddings is None:
            raise IngestionUnavailable(
                "Embeddings are disabled. Configure openai mode, select explicit test_hash mode, or inject an approved embedding adapter."
            )
        if len(documents) > 10000:
            raise ValueError("At most 10000 documents per ingestion run")
        if len({doc.record_id for doc in documents}) != len(documents):
            raise ValueError("Duplicate document IDs")
        if any(doc.metadata.get("source_type") != "SYNTHETIC" for doc in documents):
            raise ValueError("Only synthetic records are permitted by the current storage policy")
        async with self.lock:
            async with asyncio.timeout(60):
                stats = await self.store.stats()
                existing_space = stats.get("embedding_space")
                if existing_space and existing_space["name"] != self.embedding_space:
                    raise ValueError("Embedding space mismatch; use a separate index for a new model")
                previous = await self.store.fingerprints()
                changed = [(doc, doc.digest()) for doc in documents if previous.get(doc.record_id) != doc.digest()]
                records = []
                for offset in range(0, len(changed), 64):
                    batch = changed[offset : offset + 64]
                    vectors = await self.embeddings.embed([doc.searchable_text for doc, _ in batch])
                    if len(vectors) != len(batch):
                        raise ValueError("Embedding adapter returned the wrong number of vectors")
                    for (doc, digest), vector in zip(batch, vectors, strict=True):
                        records.append(
                            VectorRecord(
                                doc.record_id,
                                doc.document_type,
                                doc.searchable_text,
                                tuple(vector),
                                doc.metadata | {"content_hash": digest},
                            )
                        )
                # Cancellation must be observed before the synchronous atomic write.
                await asyncio.sleep(0)
                await self.store.upsert(records)
                return {
                    "submitted": len(documents),
                    "embedded": len(records),
                    "unchanged": len(documents) - len(records),
                    "index": await self.store.stats(),
                }

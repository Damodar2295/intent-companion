"""Contract test doubles, NOT semantic models or production retrieval infrastructure."""

import copy
import hashlib
import math
import re

from agent.retrieval.contracts import RetrievalHit
from agent.retrieval.filters import matches


def tokens(text):
    return set(re.findall(r"\w+", text.casefold()))


class TestEmbeddingAdapter:
    __test__ = False

    def __init__(self, dimensions=16):
        if dimensions < 1:
            raise ValueError("Positive embedding dimensions required")
        self.dimensions = dimensions

    async def embed(self, texts):
        result = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in tokens(text):
                vector[int.from_bytes(hashlib.sha256(token.encode()).digest()[:4]) % self.dimensions] += 1
            norm = math.sqrt(sum(v * v for v in vector)) or 1
            result.append(tuple(v / norm for v in vector))
        return result


class TestVectorStore:
    __test__ = False

    def __init__(self):
        self.records = {}
        self.dimensions = None

    async def upsert(self, records):
        dimensions = self.dimensions or (len(records[0].embedding) if records else None)
        if any(
            not r.embedding or len(r.embedding) != dimensions or any(not math.isfinite(v) for v in r.embedding)
            for r in records
        ):
            raise ValueError("Inconsistent or invalid embedding dimensions")
        self.dimensions = dimensions
        self.records.update({r.record_id: copy.deepcopy(r) for r in records})

    def filtered(self, filters):
        return [r for r in self.records.values() if matches(r.document_type, r.metadata, filters)]

    async def semantic_search(self, embedding, filters, top_k):
        if self.dimensions is not None and len(embedding) != self.dimensions:
            raise ValueError("Query embedding dimension mismatch")
        hits = [
            RetrievalHit(
                copy.deepcopy(r),
                sum(a * b for a, b in zip(embedding, r.embedding, strict=True)),
                "test_hash_dot_product",
            )
            for r in self.filtered(filters)
        ]
        return sorted(hits, key=lambda h: (-h.score, h.record.record_id))[: max(0, top_k)]

    async def lexical_search(self, query, filters, top_k):
        hits = [
            RetrievalHit(copy.deepcopy(r), float(len(tokens(query) & tokens(r.searchable_text))), "test_token_overlap")
            for r in self.filtered(filters)
        ]
        return sorted(hits, key=lambda h: (-h.score, h.record.record_id))[: max(0, top_k)]

    async def delete(self, record_ids):
        for identity in record_ids:
            self.records.pop(identity, None)


class TestRerankerAdapter:
    __test__ = False

    async def rerank(self, query, candidates, top_k):
        hits = [
            RetrievalHit(
                h.record, float(len(tokens(query) & tokens(h.record.searchable_text))), "test_reranker_overlap"
            )
            for h in candidates
        ]
        return sorted(hits, key=lambda h: (-h.score, h.record.record_id))[: max(0, top_k)]

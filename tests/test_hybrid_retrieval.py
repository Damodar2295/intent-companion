import asyncio

import pytest

from agent.retrieval.contracts import RetrievalHit, VectorRecord
from agent.retrieval.hybrid import HybridRetriever, fuse
from agent.retrieval.models import RetrievalRequest
from agent.retrieval.testing import TestEmbeddingAdapter, TestVectorStore


def record(identity, text, kind="benefit", **metadata):
    return VectorRecord(identity, kind, text, (1.0, 0.0), {"source_type": "SYNTHETIC", "market": "US", **metadata})


@pytest.mark.asyncio
async def test_fuse_uses_rrf_and_deduplicates():
    a, b, c = record("a", "dining"), record("b", "travel"), record("c", "culture")
    lexical = [RetrievalHit(a, 100, "bm25"), RetrievalHit(b, 50, "bm25")]
    semantic = [RetrievalHit(b, 0.99, "cosine"), RetrievalHit(a, 0.98, "cosine"), RetrievalHit(c, 0.1, "cosine")]
    hits, conflicts, unique = fuse(lexical, semantic, 60, 3)
    assert conflicts == 0 and unique == 3
    assert [h.record_id for h in hits] == ["a", "b", "c"]
    assert hits[0].lexical_rank == 1 and hits[0].semantic_rank == 2
    assert hits[0].rrf_score == pytest.approx(1 / 61 + 1 / 62)


@pytest.mark.asyncio
async def test_hybrid_filters_before_channels_and_exposes_debug(tmp_path, settings):
    store = TestVectorStore()
    embed = TestEmbeddingAdapter(2)
    await store.upsert(
        [
            record("rome", "Rome dining", city="Rome", category="DINING", expires_at="2030-01-01T00:00:00+00:00"),
            record("paris", "Paris dining", city="Paris", category="DINING", expires_at="2030-01-01T00:00:00+00:00"),
            record("expired", "Rome culture", city="Rome", category="CULTURE", expires_at="2020-01-01T00:00:00+00:00"),
        ]
    )
    settings.retrieval_timeout = 2
    retriever = HybridRetriever(store, embed, settings)
    result = await retriever.search(
        RetrievalRequest(
            customer_id="cust-dining",
            consent={"allowed": True},
            query="Rome dining",
            filters={"city": "Rome"},
            debug=True,
        ),
        "US",
    )
    assert result.status == "READY"
    assert [h.record_id for h in result.hits] == ["rome"]
    assert result.mode == "hybrid"
    assert result.debug["filtered_lexical_candidates"] == 1
    assert result.debug["filters"]["city"] == "Rome"


@pytest.mark.asyncio
async def test_lexical_only_when_embeddings_disabled(settings):
    store = TestVectorStore()
    await store.upsert([record("a", "Rome dining", city="Rome", expires_at="2030-01-01T00:00:00+00:00")])
    result = await HybridRetriever(store, None, settings).search(
        RetrievalRequest(customer_id="cust-dining", consent={"allowed": True}, query="Rome dining"), "US"
    )
    assert result.mode == "lexical_only"
    assert result.warnings == ["semantic retrieval disabled."]


@pytest.mark.asyncio
async def test_failed_semantic_branch_is_partial(settings):
    class Bad:
        async def embed(self, _):
            raise RuntimeError("provider secret")

    store = TestVectorStore()
    await store.upsert([record("a", "Rome dining", expires_at="2030-01-01T00:00:00+00:00")])
    result = await HybridRetriever(store, Bad(), settings).search(
        RetrievalRequest(customer_id="cust-dining", consent={"allowed": True}, query="Rome dining"), "US"
    )
    assert result.status == "PARTIAL" and result.mode == "lexical_only"
    assert "provider secret" not in str(result)


@pytest.mark.asyncio
async def test_semantic_timeout_is_bounded(settings):
    class Slow:
        async def embed(self, _):
            await asyncio.sleep(1)
            return [(1, 0)]

    store = TestVectorStore()
    await store.upsert([record("a", "Rome dining", expires_at="2030-01-01T00:00:00+00:00")])
    settings.retrieval_timeout = 0.01
    result = await HybridRetriever(store, Slow(), settings).search(
        RetrievalRequest(customer_id="cust-dining", consent={"allowed": True}, query="Rome dining"), "US"
    )
    assert result.status == "PARTIAL" and any("timed_out" in warning for warning in result.warnings)


def test_request_limits():
    with pytest.raises(ValueError):
        RetrievalRequest(customer_id="x", consent={"allowed": True}, query="x", top_k=2, candidate_k=1)

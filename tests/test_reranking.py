import asyncio

import pytest

from agent.retrieval.contracts import RetrievalHit, VectorRecord
from agent.retrieval.hybrid import HybridRetriever
from agent.retrieval.models import RetrievalRequest
from agent.retrieval.testing import TestEmbeddingAdapter, TestRerankerAdapter, TestVectorStore


def rec(i, text):
    return VectorRecord(
        i,
        "benefit",
        text,
        (1.0, 0.0),
        {"market": "US", "source_type": "SYNTHETIC", "expires_at": "2030-01-01T00:00:00+00:00"},
    )


@pytest.mark.asyncio
async def test_reranker_scores_are_separate_and_acceptance_is_thresholded(settings):
    store = TestVectorStore()
    await store.upsert([rec("a", "Rome dining"), rec("b", "Rome museum")])
    settings.reranker_threshold = 1.5
    result = await HybridRetriever(store, TestEmbeddingAdapter(2), settings, TestRerankerAdapter()).search(
        RetrievalRequest(
            customer_id="cust-dining", consent={"allowed": True}, query="Rome dining", top_k=2, debug=True
        ),
        "US",
    )
    assert result.status == "READY"
    assert result.debug["reranker"] == "SUCCEEDED"
    assert all(h.reranker_score is not None for h in result.hits)
    assert all(h.rrf_score != h.reranker_score for h in result.hits)
    assert result.hits[0].acceptance == "ACCEPTED"
    assert any(h.acceptance == "BELOW_THRESHOLD" for h in result.hits)


@pytest.mark.asyncio
async def test_disabled_reranker_does_not_claim_acceptance(settings):
    store = TestVectorStore()
    await store.upsert([rec("a", "Rome dining")])
    result = await HybridRetriever(store, TestEmbeddingAdapter(2), settings).search(
        RetrievalRequest(customer_id="cust-dining", consent={"allowed": True}, query="Rome dining"), "US"
    )
    assert result.hits[0].acceptance == "NOT_RERANKED"
    assert result.hits[0].reranker_score is None


@pytest.mark.asyncio
async def test_reranker_failure_retains_fused_order(settings):
    class Broken:
        async def rerank(self, *_):
            raise RuntimeError("secret provider body")

    store = TestVectorStore()
    await store.upsert([rec("a", "Rome dining")])
    result = await HybridRetriever(store, TestEmbeddingAdapter(2), settings, Broken()).search(
        RetrievalRequest(customer_id="cust-dining", consent={"allowed": True}, query="Rome dining", debug=True), "US"
    )
    assert result.status == "PARTIAL"
    assert result.debug["reranker"] == "FAILED"
    assert result.hits[0].reranker_score is None
    assert "secret provider" not in str(result)


@pytest.mark.asyncio
async def test_reranker_timeout_retains_fused_order(settings):
    class Slow:
        async def rerank(self, *_):
            await asyncio.sleep(1)

    store = TestVectorStore()
    await store.upsert([rec("a", "Rome dining")])
    settings.retrieval_timeout = 0.01
    result = await HybridRetriever(store, TestEmbeddingAdapter(2), settings, Slow()).search(
        RetrievalRequest(customer_id="cust-dining", consent={"allowed": True}, query="Rome dining", debug=True), "US"
    )
    assert result.status == "PARTIAL" and result.debug["reranker"] == "TIMED_OUT"


def test_reranker_contract_preserves_raw_hit_scores():
    hit = RetrievalHit(rec("a", "Rome dining"), 0.5, "rrf")
    assert hit.score_type == "rrf" and hit.score == 0.5

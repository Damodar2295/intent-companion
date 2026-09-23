import pytest

from agent.providers.catalog import SQLiteCatalogProvider, UnavailableAmexExperienceProvider
from agent.providers.contracts import CapabilityUnavailable, CatalogQuery
from agent.retrieval.contracts import VectorRecord
from agent.retrieval.testing import TestEmbeddingAdapter, TestRerankerAdapter, TestVectorStore


async def test_catalog_providers_preserve_repository_objects(repository):
    provider = SQLiteCatalogProvider(repository)
    query = CatalogQuery("US", "consumer", "Rome")
    rows = []
    for method in [provider.cards, provider.benefits, provider.offers, provider.rewards, provider.merchants]:
        rows.extend(await method(query))
    assert {r.item_id: r for r in rows} == {r.item_id: r for r in repository.catalog("US", "consumer", "Rome")}
    assert not await provider.cards(CatalogQuery("unknown", "consumer", "Rome"))


async def test_unavailable_experience_is_explicit():
    with pytest.raises(CapabilityUnavailable):
        await UnavailableAmexExperienceProvider().search(None)


async def test_retrieval_doubles_filters_updates_delete_and_dimensions():
    embedding, store, reranker = TestEmbeddingAdapter(), TestVectorStore(), TestRerankerAdapter()
    vectors = await embedding.embed(["dining Rome", "dining Paris"])
    await store.upsert(
        [
            VectorRecord("a", "benefit", "dining Rome", vectors[0], {"city": "Rome"}),
            VectorRecord("b", "benefit", "dining Paris", vectors[1], {"city": "Paris"}),
        ]
    )
    hits = await store.semantic_search(vectors[0], {"city": "Rome"}, 5)
    assert [h.record.record_id for h in hits] == ["a"]
    assert hits[0].score_type.startswith("test_")
    assert [h.record.record_id for h in await reranker.rerank("dining", hits, 1)] == ["a"]
    await store.upsert([VectorRecord("a", "benefit", "updated Rome", vectors[0], {"city": "Rome"})])
    assert (await store.lexical_search("updated", {"city": "Rome"}, 1))[0].record.searchable_text == "updated Rome"
    with pytest.raises(ValueError):
        await store.semantic_search((1.0,), {}, 1)
    await store.delete(["a"])
    assert not await store.semantic_search(vectors[0], {"city": "Rome"}, 1)

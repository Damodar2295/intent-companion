import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from agent.main import create_app
from agent.retrieval.composition import build_ingestion
from agent.retrieval.documents import clean, seed_documents
from agent.retrieval.ingestion import IngestionService, IngestionUnavailable
from agent.retrieval.sqlite import SQLiteVectorStore
from agent.retrieval.testing import TestEmbeddingAdapter
from config.settings import ROOT, Settings


@pytest.fixture
def documents():
    return seed_documents(ROOT / "data")


def test_typed_search_text_and_provenance(documents):
    assert len(documents) == 44
    assert len({d.record_id for d in documents}) == 44
    assert {d.document_type for d in documents} == {
        "card",
        "benefit",
        "offer",
        "reward",
        "merchant",
        "place",
        "event",
        "experience",
    }
    assert all(d.metadata["source_type"] == "SYNTHETIC" and d.metadata["expires_at"] for d in documents)
    assert all("Source: SYNTHETIC" in d.searchable_text for d in documents)
    assert all(not d.record_id.startswith(("customer:", "signal:")) for d in documents)
    events = [d for d in documents if d.document_type == "event"]
    assert len(events) == 6 and len({d.digest() for d in events}) == 6
    assert all("Venue:" in d.searchable_text and "Starts:" in d.searchable_text for d in events)
    assert clean("  Rome\n   Ｄining  ") == "Rome Dining"
    benefit = next(d for d in documents if d.document_type == "benefit")
    assert "Conditions:" in benefit.searchable_text and "Products:" in benefit.searchable_text
    experience = next(d for d in documents if d.document_type == "experience")
    assert experience.metadata["relationship_evidence"]


async def test_persistence_idempotence_versioning_filters_and_delete(tmp_path, documents):
    path = str(tmp_path / "index.sqlite3")
    store = SQLiteVectorStore(path, "test-hash-v1:16")
    embedder = TestEmbeddingAdapter()
    service = IngestionService(store, embedder, "test-hash-v1:16")
    first = await service.ingest(documents)
    assert first["embedded"] == 44
    assert (await service.ingest(documents))["unchanged"] == 44
    store.close()
    store = SQLiteVectorStore(path, "test-hash-v1:16")
    try:
        service = IngestionService(store, embedder, "test-hash-v1:16")
        assert (await store.stats())["records"] == 44
        hits = await store.lexical_search('Rome OR " *', {"city": "Rome", "document_type": "event"}, 5)
        assert len(hits) == 2 and all(h.record.metadata["document_version"] == 1 for h in hits)
        changed = documents[0].model_copy(deep=True)
        changed.searchable_text += "\nDescription: additional synthetic detail"
        report = await service.ingest([changed])
        assert report["embedded"] == 1
        hits = await store.lexical_search("additional synthetic detail", {"document_type": "card"}, 10)
        updated = next(h.record for h in hits if h.record.record_id == changed.record_id)
        assert updated.metadata["document_version"] == 2
        query = (await embedder.embed(["Rome culture"]))[0]
        vector_hits = await store.semantic_search(query, {"city": "Rome", "document_type": "event"}, 2)
        assert len(vector_hits) == 2 and vector_hits[0].score_type == "test_hash_cosine"
        assert all(h.record.metadata["city"] == "Rome" for h in vector_hits)
        await store.delete([changed.record_id])
        assert (await store.stats())["records"] == 43
        assert changed.record_id not in await store.fingerprints()
        assert all(h.record.record_id != changed.record_id for h in await store.lexical_search("additional", {}, 100))
    finally:
        store.close()


async def test_embedding_failure_and_cancellation_do_not_publish(documents):
    store = SQLiteVectorStore(":memory:", "test-hash-v1:16")

    class Broken:
        async def embed(self, texts):
            raise RuntimeError("embedding unavailable")

    try:
        with pytest.raises(RuntimeError):
            await IngestionService(store, Broken(), "test-hash-v1:16").ingest(documents)
        assert (await store.stats())["records"] == 0
        started = asyncio.Event()

        class Slow:
            async def embed(self, texts):
                started.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(IngestionService(store, Slow(), "test-hash-v1:16").ingest(documents))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await store.stats())["records"] == 0
    finally:
        store.close()


@pytest.mark.parametrize("vector", [(), (float("nan"),) * 16, (0.0,) * 16, (1.0,) * 8])
async def test_invalid_vectors_atomic(documents, vector):
    store = SQLiteVectorStore(":memory:", "test-hash-v1:16")
    try:
        await IngestionService(store, TestEmbeddingAdapter(), "test-hash-v1:16").ingest(documents[:1])
        hit = (await store.lexical_search("Rome", {}, 1))[0].record
        invalid = replace(hit, record_id="bad", embedding=vector)
        with pytest.raises(ValueError):
            await store.upsert([replace(hit, record_id="new"), invalid])
        assert (await store.stats())["records"] == 1
    finally:
        store.close()


async def test_disabled_missing_and_changed_embedding_space(documents, tmp_path):
    disabled = build_ingestion(Settings(database_path=":memory:"))
    try:
        with pytest.raises(IngestionUnavailable):
            await disabled.ingest(documents)
        assert (await disabled.store.stats())["records"] == 0
    finally:
        disabled.store.close()
    path = str(tmp_path / "models.sqlite3")
    store = SQLiteVectorStore(path, "test-hash-v1:16")
    await IngestionService(store, TestEmbeddingAdapter(), "test-hash-v1:16").ingest(documents)
    store.close()
    store = SQLiteVectorStore(path, "different-model")
    try:
        with pytest.raises(ValueError, match="space mismatch"):
            await IngestionService(store, TestEmbeddingAdapter(), "different-model").ingest(documents)
        with pytest.raises(ValueError, match="space or dimension"):
            await store.semantic_search((1.0,) * 16, {}, 1)
    finally:
        store.close()


async def test_non_synthetic_and_duplicate_inputs_rejected(documents):
    store = SQLiteVectorStore(":memory:", "test-hash-v1:16")
    try:
        service = IngestionService(store, TestEmbeddingAdapter(), "test-hash-v1:16")
        with pytest.raises(ValueError, match="Duplicate"):
            await service.ingest([documents[0], documents[0]])
        forbidden = documents[0].model_copy(deep=True)
        forbidden.metadata["source_type"] = "PLACES_API"
        with pytest.raises(ValueError, match="synthetic"):
            await service.ingest([forbidden])
        assert (await store.stats())["records"] == 0
    finally:
        store.close()


async def test_stats_api_reads_persisted_index(tmp_path, documents):
    path = str(tmp_path / "companion.sqlite3")
    settings = Settings(database_path=path, embedding_mode="test_hash")
    service = build_ingestion(settings)
    await service.ingest(documents)
    service.store.close()
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/infrastructure/index")
        assert response.status_code == 200
        result = response.json()
        assert result["records"] == 44 and result["by_type"]["event"] == 6
        assert result["semantic_quality_verified"] is False
        assert result["customer_retrieval_enabled"] is False
        assert str(tmp_path) not in response.text
        assert client.get("/api/scenarios").status_code == 200


async def test_sql_failure_rolls_back_documents_and_fts(documents):
    import sqlite3

    store = SQLiteVectorStore(":memory:", "test-hash-v1:16")
    try:
        store.db.execute("""CREATE TRIGGER reject_benefit BEFORE INSERT ON retrieval_documents
                            WHEN NEW.kind='benefit' BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        with pytest.raises(sqlite3.IntegrityError):
            await IngestionService(store, TestEmbeddingAdapter(), "test-hash-v1:16").ingest(documents)
        assert (await store.stats())["records"] == 0
        assert (await store.stats())["embedding_space"] is None
        assert await store.lexical_search("Rome", {}, 10) == []
    finally:
        store.close()


async def test_wrong_embedding_count_not_published(documents):
    class WrongCount:
        async def embed(self, texts):
            return []

    store = SQLiteVectorStore(":memory:", "test-hash-v1:16")
    try:
        with pytest.raises(ValueError, match="number of vectors"):
            await IngestionService(store, WrongCount(), "test-hash-v1:16").ingest(documents)
        assert (await store.stats())["records"] == 0
    finally:
        store.close()


def test_stats_failure_is_safe(client):
    client.app.state.ingestion.store.close()
    response = client.get("/api/infrastructure/index")
    assert response.status_code == 503
    assert response.json() == {"detail": "Retrieval index unavailable"}


def test_provider_metadata_change_changes_fingerprint(documents):
    original = documents[0]
    updated = original.model_copy(deep=True)
    updated.metadata["expires_at"] = "2026-10-01T00:00:00+00:00"
    assert updated.digest() != original.digest()
    assert updated.searchable_text == original.searchable_text

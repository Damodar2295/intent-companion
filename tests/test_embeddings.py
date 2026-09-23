import asyncio
import json

import httpx
import pytest

from agent.retrieval.composition import build_ingestion
from agent.retrieval.documents import seed_documents
from agent.retrieval.embeddings import EmbeddingError, OpenAIEmbeddingAdapter
from config.settings import ROOT, Settings


def settings(**changes):
    return Settings(
        database_path=":memory:",
        embedding_mode="openai",
        embedding_model="test-configured-model",
        embedding_api_key="test-private-key",
        **changes,
    )


def reply(count, dimensions=3):
    return {
        "model": "test-configured-model",
        "data": [{"index": i, "embedding": [float(i + 1)] * dimensions} for i in reversed(range(count))],
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }


async def test_real_adapter_wire_order_and_safe_logs(caplog):
    caplog.set_level("INFO", logger="embeddings")
    calls = []

    def response(req):
        body = json.loads(req.content)
        calls.append(body)
        assert req.headers["Authorization"] == "Bearer test-private-key"
        assert body["model"] == "test-configured-model" and body["encoding_format"] == "float"
        assert body["dimensions"] == 3
        return httpx.Response(200, json=reply(len(body["input"])))

    adapter = OpenAIEmbeddingAdapter(settings(embedding_output_dimensions=3), httpx.MockTransport(response))
    vectors = await adapter.embed(["private-text"] * 17)
    assert len(calls) == 2 and len(vectors) == 17
    assert vectors[0] == (1.0, 1.0, 1.0) and vectors[15] == (16.0, 16.0, 16.0)
    assert "private-text" not in caplog.text and "test-private-key" not in caplog.text
    assert '"tokens"' in caplog.text


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b.update(data=[]),
        lambda b: b.update(model="wrong-model"),
        lambda b: b["data"][0].update(index=1),
        lambda b: b["data"][0].update(embedding=[]),
        lambda b: b["data"][0].update(embedding=[True, 1, 2]),
        lambda b: b["data"][0].update(embedding=["x", 1, 2]),
        lambda b: b["data"][0].update(embedding=[0, 0, 0]),
        lambda b: b["data"][0].update(embedding=[1, 2]),
    ],
)
async def test_bad_provider_vectors_rejected(mutation):
    body = reply(1)
    mutation(body)
    adapter = OpenAIEmbeddingAdapter(
        settings(embedding_output_dimensions=3), httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    )
    with pytest.raises(EmbeddingError, match="invalid vectors"):
        await adapter.embed(["synthetic input"])


async def test_auth_error_no_retry_or_mock_fallback():
    calls = []

    def response(req):
        calls.append(req)
        return httpx.Response(401, json={"error": "provider secret message"})

    service = build_ingestion(settings(), httpx.MockTransport(response))
    try:
        with pytest.raises(EmbeddingError, match="access denied") as exc:
            await service.ingest(seed_documents(ROOT / "data")[:1])
        assert len(calls) == 1 and "provider secret" not in str(exc.value)
        assert (await service.store.stats())["records"] == 0
    finally:
        service.store.close()


async def test_transient_retries_bounded(monkeypatch):
    async def no_delay(_):
        pass

    monkeypatch.setattr("agent.retrieval.embeddings.asyncio.sleep", no_delay)
    calls = []

    def response(req):
        calls.append(req)
        return httpx.Response(503)

    adapter = OpenAIEmbeddingAdapter(settings(), httpx.MockTransport(response))
    with pytest.raises(EmbeddingError):
        await adapter.embed(["synthetic input"])
    assert len(calls) == 3


async def test_cancellation_propagates():
    started = asyncio.Event()

    async def delayed(req):
        started.set()
        await asyncio.Event().wait()

    adapter = OpenAIEmbeddingAdapter(settings(), httpx.MockTransport(delayed))
    task = asyncio.create_task(adapter.embed(["synthetic input"]))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_configuration_and_input_fail_before_network():
    config = settings()
    config.embedding_model = ""
    with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL"):
        OpenAIEmbeddingAdapter(config)
    config = settings()
    config.embedding_api_key = ""
    adapter = OpenAIEmbeddingAdapter(config)
    with pytest.raises(EmbeddingError, match="OPENAI_API_KEY"):
        await adapter.embed(["test"])
    with pytest.raises(EmbeddingError, match="HTTPS"):
        OpenAIEmbeddingAdapter(settings(embedding_endpoint="http://example.org/embeddings"))
    adapter = OpenAIEmbeddingAdapter(settings())
    for text in (" ", "a" * 8193):
        with pytest.raises(EmbeddingError, match="input"):
            await adapter.embed([text])


async def test_real_adapter_ingestion_persists_model_vectors(tmp_path):
    config = settings()
    config.database_path = str(tmp_path / "model.sqlite3")

    def response(req):
        body = json.loads(req.content)
        assert "dimensions" not in body
        return httpx.Response(200, json=reply(len(body["input"])))

    service = build_ingestion(config, httpx.MockTransport(response))
    try:
        report = await service.ingest(seed_documents(ROOT / "data"))
        assert report["embedded"] == 44
        assert report["index"]["embedding_kind"] == "model"
        assert report["index"]["embedding_space"]["dimensions"] == 3
        assert report["index"]["semantic_quality_verified"] is False
        assert (await service.ingest(seed_documents(ROOT / "data")))["embedded"] == 0
    finally:
        service.store.close()

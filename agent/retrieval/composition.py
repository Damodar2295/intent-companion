"""Local infrastructure composition; enterprise services must be explicitly injected."""

from agent.retrieval.embeddings import OpenAIEmbeddingAdapter
from agent.retrieval.ingestion import IngestionService
from agent.retrieval.sqlite import SQLiteVectorStore
from agent.retrieval.testing import TestEmbeddingAdapter


def build_ingestion(settings, transport=None):
    # No silent test embedding fallback when an enterprise provider is requested.
    if settings.embedding_mode not in {"disabled", "test_hash", "openai"}:
        raise ValueError("Embedding provider unavailable; inject an approved EmbeddingService")
    space = f"test-hash-v1:{settings.embedding_dimensions}" if settings.embedding_mode == "test_hash" else None
    embeddings = TestEmbeddingAdapter(settings.embedding_dimensions) if space else None
    if settings.embedding_mode == "openai":
        embeddings = OpenAIEmbeddingAdapter(settings, transport)
        space = embeddings.embedding_space
    store = SQLiteVectorStore(settings.retrieval_database_path or settings.database_path, space)
    return IngestionService(store, embeddings, space)

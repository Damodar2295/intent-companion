from dataclasses import dataclass, field
from typing import Protocol

from pydantic import JsonValue


@dataclass(frozen=True)
class VectorRecord:
    record_id: str
    document_type: str
    searchable_text: str
    embedding: tuple[float, ...]
    metadata: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalHit:
    record: VectorRecord
    score: float
    score_type: str


class VectorStore(Protocol):
    async def upsert(self, records: list[VectorRecord]) -> None: ...
    async def semantic_search(
        self, embedding: tuple[float, ...], filters: dict[str, JsonValue], top_k: int
    ) -> list[RetrievalHit]: ...
    async def lexical_search(self, query: str, filters: dict[str, JsonValue], top_k: int) -> list[RetrievalHit]: ...
    async def delete(self, record_ids: list[str]) -> None: ...


class EmbeddingService(Protocol):
    async def embed(self, texts: list[str]) -> list[tuple[float, ...]]: ...


class RerankerService(Protocol):
    async def rerank(self, query: str, candidates: list[RetrievalHit], top_k: int) -> list[RetrievalHit]: ...


class IngestionStore(VectorStore, Protocol):
    async def fingerprints(self) -> dict[str, str]: ...
    async def stats(self) -> dict[str, JsonValue]: ...

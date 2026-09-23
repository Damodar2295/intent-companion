from datetime import date as Date
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from agent.domain import Consent, Model

Kind = Literal["card", "benefit", "offer", "reward", "merchant", "place", "event", "experience"]


class MetadataFilters(Model):
    document_types: list[Kind] = Field(default_factory=list, max_length=8)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    segment: str | None = Field(default=None, min_length=1, max_length=100)
    product_ids: list[str] = Field(default_factory=list, max_length=12)
    valid_on: Date | None = None


class RetrievalRequest(Model):
    customer_id: str = Field(min_length=1, max_length=100)
    consent: Consent = Field(default_factory=Consent)
    query: str = Field(min_length=1, max_length=1000)
    filters: MetadataFilters = Field(default_factory=MetadataFilters)
    top_k: int = Field(default=10, ge=1, le=50)
    candidate_k: int = Field(default=30, ge=1, le=200)
    debug: bool = False

    @model_validator(mode="after")
    def valid_query(self):
        if not self.query.strip() or self.top_k > self.candidate_k:
            raise ValueError("Query must be nonblank and top_k must not exceed candidate_k")
        return self


class HybridHit(Model):
    record_id: str
    document_type: str
    searchable_text: str
    metadata: dict[str, JsonValue]
    rrf_score: float
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    lexical_score: float | None = None
    semantic_score: float | None = None
    lexical_score_type: str | None = None
    semantic_score_type: str | None = None
    reranker_score: float | None = None
    reranker_score_type: str | None = None
    acceptance: Literal["ACCEPTED", "BELOW_THRESHOLD", "NOT_RERANKED"] = "NOT_RERANKED"
    acceptance_reason: str | None = None


class RetrievalResponse(Model):
    status: Literal["READY", "EMPTY", "PARTIAL", "ERROR"]
    mode: Literal["hybrid", "lexical_only", "semantic_only", "unavailable"]
    embedding_kind: Literal["disabled", "test_hash", "openai"]
    hits: list[HybridHit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    debug: dict[str, JsonValue] | None = None
    usage: str = "Synthetic retrieval candidates only; reranking thresholding is retrieval acceptance, not eligibility or savings."

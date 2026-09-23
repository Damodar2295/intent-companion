"""Explicit settings and injectable clock. No network is needed by default."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = {
    "travel_booking": 0.9,
    "customer_declared_intent": 0.9,
    "travel_search": 0.45,
    "hotel_search": 0.4,
    "restaurant_search": 0.15,
    "restaurant_booking": 0.3,
    "ad_click": 0.1,
    "website_interaction": 0.1,
    "app_interaction": 0.1,
    "event_search": 0.15,
    "event_booking": 0.9,
}


class Settings(BaseModel):
    database_path: str = str(ROOT / "var" / "companion.sqlite3")
    fixture_dir: Path = ROOT / "data"
    retrieval_database_path: str | None = None
    embedding_mode: Literal["disabled", "test_hash", "openai"] = "disabled"
    embedding_dimensions: int = Field(default=64, ge=8, le=4096)
    embedding_model: str = ""
    embedding_api_key: str = Field(default="", repr=False, exclude=True)
    embedding_endpoint: str = "https://api.openai.com/v1/embeddings"
    embedding_output_dimensions: int | None = Field(default=None, ge=1, le=8192)
    embedding_timeout: float = Field(default=10, gt=0, le=30)
    business_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "declared_goal": 0.6,
            "supplier_search": 0.2,
            "scheduled_payment": 0.5,
            "spend_observation": 0.15,
            "employee_growth": 0.3,
        }
    )
    demo_mode: bool = True
    demo_now: datetime = datetime(2026, 9, 17, 12, tzinfo=UTC)
    signal_ttl_days: int = Field(default=30, ge=1)
    catalog_ttl_days: int = Field(default=90, ge=1)
    intent_planning_threshold: float = Field(default=0.4, ge=0, le=1)
    signal_ttl_overrides: dict[str, int] = Field(default_factory=dict)
    intent_extraction_mode: Literal["deterministic", "llm", "mock"] = "deterministic"
    retrieval_rrf_k: int = Field(default=60, ge=1, le=1000)
    retrieval_timeout: float = Field(default=10, gt=0, le=30)
    retrieval_concurrency: int = Field(default=4, ge=1, le=8)
    reranker_mode: Literal["disabled", "test_hash"] = "disabled"
    reranker_threshold: float = Field(default=0.25, ge=0, le=1)
    reranker_top_k: int = Field(default=20, ge=1, le=50)
    tool_concurrency: int = Field(default=4, ge=1, le=8)
    tool_max_calls: int = Field(default=10, ge=1, le=10)
    tool_timeout: float = Field(default=8, gt=0, le=30)
    tool_run_deadline: float = Field(default=30, gt=0, le=60)
    tool_result_limit: int = Field(default=20, ge=1, le=100)
    search_plan_mode: Literal["auto", "mock", "llm"] = "auto"
    search_plan_timeout: float = Field(default=15, gt=0, le=30)
    weights: dict[str, float] = Field(default_factory=lambda: WEIGHTS.copy())
    ai_provider: str = "deterministic"
    llm_gateway_mode: str = "configured"
    llm_routes: dict[str, dict[str, str]] = Field(default_factory=dict)
    llm_endpoint: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout: float = Field(default=8, gt=0, le=30)

    @field_validator("demo_now")
    @classmethod
    def aware_clock(cls, value):
        if value.tzinfo is None:
            raise ValueError("DEMO_NOW must include a UTC offset")
        return value

    @field_validator("business_weights")
    @classmethod
    def valid_business_weights(cls, value):
        expected = {"declared_goal", "supplier_search", "scheduled_payment", "spend_observation", "employee_growth"}
        if set(value) != expected or any(not 0 <= weight <= 1 for weight in value.values()):
            raise ValueError("Business weights require all known event types and values from 0 to 1")
        return value

    @field_validator("weights")
    @classmethod
    def valid_weights(cls, value):
        if set(value) != set(WEIGHTS) or any(not 0 <= weight <= 1 for weight in value.values()):
            raise ValueError("Intent weights require all known signal types with values from 0 to 1")
        return value

    @field_validator("signal_ttl_overrides")
    @classmethod
    def valid_ttls(cls, value):
        if set(value) - set(WEIGHTS) or any(days < 1 for days in value.values()):
            raise ValueError("Signal TTL overrides require known types and positive days")
        return value

    def now(self) -> datetime:
        return self.demo_now if self.demo_mode else datetime.now(UTC)

    @classmethod
    def from_env(cls) -> "Settings":
        weights = WEIGHTS | json.loads(os.getenv("INTENT_WEIGHTS_JSON", "{}"))
        if set(weights) != set(WEIGHTS) or any(
            not isinstance(v, (float, int)) or not 0 <= v <= 1 for v in weights.values()
        ):
            raise ValueError("Intent weights must be known signal types with values between 0 and 1")
        provider = os.getenv("AI_PROVIDER", "deterministic")
        if provider not in {"deterministic", "llm"}:
            raise ValueError("AI_PROVIDER must be deterministic or llm")
        return cls(
            retrieval_database_path=os.getenv("RETRIEVAL_DATABASE_PATH") or None,
            embedding_mode=os.getenv("EMBEDDING_MODE", "disabled"),
            embedding_model=os.getenv("EMBEDDING_MODEL", ""),
            embedding_api_key=os.getenv("OPENAI_API_KEY", ""),
            embedding_endpoint=os.getenv("EMBEDDING_ENDPOINT", "https://api.openai.com/v1/embeddings"),
            embedding_output_dimensions=int(os.environ["EMBEDDING_OUTPUT_DIMENSIONS"])
            if os.getenv("EMBEDDING_OUTPUT_DIMENSIONS")
            else None,
            embedding_timeout=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "10")),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "64")),
            fixture_dir=Path(os.getenv("FIXTURE_DIR", str(ROOT / "data"))),
            demo_now=datetime.fromisoformat(os.getenv("DEMO_NOW", "2026-09-17T12:00:00+00:00")),
            business_weights=cls.model_fields["business_weights"].default_factory()
            | json.loads(os.getenv("BUSINESS_WEIGHTS_JSON", "{}")),
            database_path=os.getenv("DATABASE_PATH", str(ROOT / "var" / "companion.sqlite3")),
            demo_mode=os.getenv("DEMO_MODE", "true").lower() == "true",
            ai_provider=provider,
            llm_gateway_mode=os.getenv("LLM_GATEWAY_MODE", "configured"),
            llm_routes=json.loads(os.getenv("LLM_ROUTES_JSON", "{}")),
            weights=weights,
            intent_planning_threshold=float(os.getenv("INTENT_PLANNING_THRESHOLD", "0.4")),
            signal_ttl_overrides=json.loads(os.getenv("SIGNAL_TTL_DAYS_JSON", "{}")),
            retrieval_rrf_k=int(os.getenv("RETRIEVAL_RRF_K", "60")),
            retrieval_timeout=float(os.getenv("RETRIEVAL_TIMEOUT_SECONDS", "10")),
            retrieval_concurrency=int(os.getenv("RETRIEVAL_CONCURRENCY", "4")),
            reranker_mode=os.getenv("RERANKER_MODE", "disabled"),
            reranker_threshold=float(os.getenv("RERANKER_THRESHOLD", "0.25")),
            reranker_top_k=int(os.getenv("RERANKER_TOP_K", "20")),
            tool_concurrency=int(os.getenv("TOOL_CONCURRENCY", "4")),
            tool_max_calls=int(os.getenv("TOOL_MAX_CALLS", "10")),
            tool_timeout=float(os.getenv("TOOL_TIMEOUT_SECONDS", "8")),
            tool_run_deadline=float(os.getenv("TOOL_RUN_DEADLINE_SECONDS", "30")),
            tool_result_limit=int(os.getenv("TOOL_RESULT_LIMIT", "20")),
            search_plan_mode=os.getenv("SEARCH_PLAN_MODE", "auto"),
            search_plan_timeout=float(os.getenv("SEARCH_PLAN_TIMEOUT_SECONDS", "15")),
            intent_extraction_mode=os.getenv("INTENT_EXTRACTION_MODE", "deterministic"),
            llm_endpoint=os.getenv("LLM_ENDPOINT", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "8")),
        )

"""Explicit settings and injectable clock. No network is needed by default."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

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
}


class Settings(BaseModel):
    database_path: str = str(ROOT / "var" / "companion.sqlite3")
    fixture_dir: Path = ROOT / "data"
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
    weights: dict[str, float] = Field(default_factory=lambda: WEIGHTS.copy())
    ai_provider: str = "deterministic"
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
            fixture_dir=Path(os.getenv("FIXTURE_DIR", str(ROOT / "data"))),
            demo_now=datetime.fromisoformat(os.getenv("DEMO_NOW", "2026-09-17T12:00:00+00:00")),
            business_weights=cls.model_fields["business_weights"].default_factory()
            | json.loads(os.getenv("BUSINESS_WEIGHTS_JSON", "{}")),
            database_path=os.getenv("DATABASE_PATH", str(ROOT / "var" / "companion.sqlite3")),
            demo_mode=os.getenv("DEMO_MODE", "true").lower() == "true",
            ai_provider=provider,
            weights=weights,
            llm_endpoint=os.getenv("LLM_ENDPOINT", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "8")),
        )

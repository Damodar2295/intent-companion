import os
from datetime import UTC, datetime

from pydantic import Field, model_validator

from agent.domain import Model


class OutingSettings(Model):
    realtime: bool = False
    demo: bool = True
    openai_key: str = Field(default="", repr=False)
    model: str = ""
    responses_endpoint: str = "https://api.openai.com/v1/responses"
    search_key: str = Field(default="", repr=False)
    places_key: str = Field(default="", repr=False)
    routing_key: str = Field(default="", repr=False)
    event_key: str = Field(default="", repr=False)
    deadline: float = Field(default=60, ge=1, le=120)
    provider_timeout: float = Field(default=8, ge=1, le=30)
    debug: bool = False
    official_hosts: list[str] = Field(default_factory=list)
    merchant_mappings: list[dict] = Field(default_factory=list)
    field_source_priority: dict[str, dict[str, int]] = Field(default_factory=dict)
    price_table: dict[str, dict[str, float]] = Field(default_factory=dict)
    catalog_refresh_days: int = Field(default=30, ge=1, le=90)
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "relevance": 0.30,
            "preferences": 0.20,
            "evidence": 0.20,
            "travel": 0.15,
            "budget": 0.10,
            "value": 0.05,
        }
    )
    ttl: dict[str, int] = Field(
        default_factory=lambda: {
            "route": 300,
            "availability": 300,
            "opening_status": 3600,
            "opening_hours": 21600,
            "schedule.start": 21600,
            "schedule.end": 21600,
            "price": 3600,
            "default": 21600,
        }
    )
    source_priority: dict[str, int] = Field(
        default_factory=lambda: {
            "OFFICIAL_ORGANIZER": 100,
            "OFFICIAL_VENUE": 95,
            "TICKETING_API": 90,
            "PLACES_API": 90,
            "TOURISM_AUTHORITY": 80,
            "DEMO": 90,
        }
    )

    @model_validator(mode="after")
    def mode(self):
        if self.realtime == self.demo:
            raise ValueError("Choose exactly one: REALTIME_MODE or DEMO_MODE")
        if set(self.weights) != {"relevance", "preferences", "evidence", "travel", "budget", "value"}:
            raise ValueError("Outing weights must contain all six ranking signals")
        if any(v < 0 for v in self.weights.values()) or abs(sum(self.weights.values()) - 1) > 0.001:
            raise ValueError("Outing ranking weights must be nonnegative and total 1")
        if any(v <= 0 for v in self.ttl.values()):
            raise ValueError("TTL values must be positive")
        return self

    @classmethod
    def from_env(cls):
        import json

        for name, expected in [
            ("SEARCH_PROVIDER", "brave"),
            ("PLACES_PROVIDER", "google"),
            ("ROUTING_PROVIDER", "google"),
            ("EVENT_PROVIDER", "ticketmaster"),
            ("AMEX_DATA_MODE", "synthetic"),
        ]:
            if os.getenv(name, expected) != expected:
                raise ValueError(f"{name} is unsupported; expected {expected}")
        return cls(
            realtime=os.getenv("REALTIME_MODE", "false").lower() == "true",
            demo=os.getenv("DEMO_MODE", "true").lower() == "true",
            openai_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", ""),
            responses_endpoint=os.getenv("OPENAI_RESPONSES_ENDPOINT", "https://api.openai.com/v1/responses"),
            search_key=os.getenv("SEARCH_API_KEY", ""),
            places_key=os.getenv("PLACES_API_KEY", ""),
            routing_key=os.getenv("ROUTING_API_KEY", ""),
            event_key=os.getenv("EVENT_API_KEY", ""),
            deadline=float(os.getenv("OUTING_DEADLINE_SECONDS", "60")),
            provider_timeout=float(os.getenv("OUTING_PROVIDER_TIMEOUT_SECONDS", "8")),
            catalog_refresh_days=int(os.getenv("OUTING_CATALOG_REFRESH_DAYS", "30")),
            debug=os.getenv("OUTING_DEBUG", "false").lower() == "true",
            official_hosts=[h.strip() for h in os.getenv("OFFICIAL_SOURCE_HOSTS", "").split(",") if h.strip()],
            **{
                key: json.loads(os.environ[env])
                for key, env in [
                    ("weights", "OUTING_RANKING_WEIGHTS"),
                    ("ttl", "OUTING_TTL_POLICY"),
                    ("source_priority", "OUTING_SOURCE_PRIORITY"),
                    ("field_source_priority", "OUTING_FIELD_SOURCE_PRIORITY"),
                    ("price_table", "OUTING_LLM_PRICE_TABLE"),
                    ("merchant_mappings", "OUTING_MERCHANT_MAPPINGS"),
                ]
                if env in os.environ
            },
        )

    def now(self):
        return datetime.now(UTC)

    def capabilities(self):
        return {
            "mode": "demo" if self.demo else "realtime",
            "amex": "synthetic",
            "llm": self.demo or bool(self.openai_key and self.model),
            "search": self.demo or bool(self.search_key),
            "places": self.demo or bool(self.places_key),
            "routing": self.demo or bool(self.routing_key),
            "events": self.demo or bool(self.event_key),
        }

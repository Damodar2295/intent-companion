"""Additional knowledge schemas; these records are not live discovery inventory."""

from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from agent.domain import Model
from agent.outing.models import Location

Identity = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Currency = Annotated[str, StringConstraints(pattern="^[A-Z]{3}$")]
SourceType = Literal["SYNTHETIC", "OFFICIAL", "PROVIDER", "DISCOVERY"]


class Source(Model):
    source_id: Identity
    source_type: SourceType
    publisher: Identity
    url: str = Field(min_length=1)
    retrieved_at: AwareDatetime
    verified_at: AwareDatetime | None = None
    expires_at: AwareDatetime
    freshness_policy: Identity
    data_completeness: Literal["COMPLETE", "PARTIAL", "UNKNOWN"] = "UNKNOWN"
    attribution: str

    @model_validator(mode="after")
    def valid_source(self):
        from urllib.parse import urlparse

        url = urlparse(self.url)
        if self.source_type == "SYNTHETIC":
            if url.scheme != "synthetic":
                raise ValueError("Synthetic source URLs must use synthetic:")
        elif url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("Source URL must be a public HTTP(S) reference without credentials")
        if self.expires_at <= self.retrieved_at:
            raise ValueError("Source expiry must follow retrieval")
        if self.verified_at and not self.retrieved_at <= self.verified_at < self.expires_at:
            raise ValueError("Source verification must fall within its freshness window")
        if self.source_type == "DISCOVERY" and self.verified_at:
            raise ValueError("Discovery alone cannot establish verified facts")
        return self


class KnowledgeRecord(Model):
    name: Identity
    description: str = Field(min_length=1)
    source_type: SourceType
    source_ids: list[Identity] = Field(min_length=1)
    market: Identity
    country: str = Field(pattern="^[A-Z]{2}$")
    city: Identity
    category: Identity
    active: bool = True
    data_completeness: Literal["COMPLETE", "PARTIAL", "UNKNOWN"] = "PARTIAL"


class Place(KnowledgeRecord):
    place_id: Identity
    address: str | None = None
    location: Location | None = None
    merchant_id: Identity | None = None
    # Unknown opening hours and availability stay unknown; not guessed from a category.


class Event(KnowledgeRecord):
    event_id: Identity
    venue_id: Identity
    ticket_seller_id: Identity | None = None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    timezone: str
    status: Literal["SCHEDULED", "CANCELLED", "POSTPONED", "UNKNOWN"] = "UNKNOWN"
    price: Decimal | None = Field(default=None, ge=0)
    currency: Currency | None = None
    availability: Literal["AVAILABLE", "SOLD_OUT", "UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def valid_event(self):
        try:
            zone = ZoneInfo(self.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("Event timezone must be an IANA timezone") from exc
        if self.ends_at <= self.starts_at:
            raise ValueError("Event end must follow start")
        for value in (self.starts_at, self.ends_at):
            if value.utcoffset() != value.astimezone(zone).utcoffset():
                raise ValueError("Event timestamp offset must match its destination timezone")
        if (self.price is None) != (self.currency is None):
            raise ValueError("Event price and currency must be supplied together")
        return self


class AmexExperience(KnowledgeRecord):
    experience_id: Identity
    event_id: Identity | None = None
    venue_id: Identity | None = None
    eligible_product_ids: list[Identity] = Field(min_length=1)
    conditions: list[Identity] = Field(min_length=1)
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    # Linking a venue is descriptive. It does not authorize a benefit for an event.
    relationship_evidence_ids: list[Identity] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_experience(self):
        if self.valid_to <= self.valid_from:
            raise ValueError("Experience validity end must follow start")
        if (self.event_id or self.venue_id) and not self.relationship_evidence_ids:
            raise ValueError("Experience relationships require explicit evidence references")
        return self

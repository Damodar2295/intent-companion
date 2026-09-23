from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, JsonValue, field_validator, model_validator

from agent.domain import Model

Category = Literal["EVENT", "CULTURE", "DINING", "SHOPPING", "ATTRACTION", "EXPERIENCE"]


class Location(Model):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class SearchPlan(Model):
    city: str = Field(min_length=1, max_length=100)
    date: date
    timezone: str
    start_time: time = time(17)
    end_time: time = time(23)
    categories: list[Category] = Field(min_length=1, max_length=6)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str = Field(default="EUR", pattern="^[A-Z]{3}$")
    travel_mode: Literal["WALK", "DRIVE", "TRANSIT"] = "WALK"
    number_of_people: int = Field(default=1, ge=1, le=12)
    user_location: Location | None = None

    @field_validator("timezone")
    @classmethod
    def zone(cls, v):
        try:
            ZoneInfo(v)
        except (ValueError, KeyError) as exc:
            raise ValueError("Select a valid destination timezone") from exc
        return v

    @model_validator(mode="after")
    def ordered(self):
        if self.start_time.tzinfo is not None or self.end_time.tzinfo is not None:
            raise ValueError("Enter local times without offsets; use the destination timezone field")
        for local_time in (self.start_time, self.end_time):
            local = datetime.combine(self.date, local_time, ZoneInfo(self.timezone))
            if local.astimezone(UTC).astimezone(ZoneInfo(self.timezone)).replace(tzinfo=None) != local.replace(
                tzinfo=None
            ):
                raise ValueError("The selected time does not exist due to a daylight-saving transition")
            if local.utcoffset() != local.replace(fold=1).utcoffset():
                raise ValueError("The selected time is ambiguous due to a daylight-saving transition")
        if self.end_time <= self.start_time:
            raise ValueError("End time must follow start time on the selected day")
        return self


class OutingRequest(Model):
    customer_id: str
    text: str = Field(min_length=3, max_length=1500)
    city: str = Field(default="Rome", min_length=1, max_length=100)
    date: date
    timezone: str = "Europe/Rome"
    start_time: time = time(17)
    end_time: time = time(23)
    travel_mode: Literal["WALK", "DRIVE", "TRANSIT"] = "WALK"
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str = Field(default="EUR", pattern="^[A-Z]{3}$")
    number_of_people: int = Field(default=1, ge=1, le=12)
    user_location: Location | None = None
    card_id: str | None = None
    visit_minutes: int = Field(default=60, ge=15, le=180)
    confirmed_condition_ids: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_plan_inputs(self):
        SearchPlan(**self.model_dump(include=set(SearchPlan.model_fields)), categories=["DINING"])
        return self


class FieldEvidence(Model):
    evidence_id: str
    field: str
    value: JsonValue
    source_type: str
    url: str
    provider: str
    retrieved_at: datetime
    expires_at: datetime
    confidence: float = Field(ge=0, le=1)
    synthetic: bool = False
    attribution: str = ""

    @model_validator(mode="after")
    def timestamps(self):
        if self.retrieved_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Evidence timestamps must be timezone aware")
        if self.expires_at < self.retrieved_at:
            raise ValueError("Evidence expiry precedes retrieval")
        return self


class DiscoveryCandidate(Model):
    candidate_id: str
    name: str
    category: Category
    provider: str
    url: str
    evidence: list[FieldEvidence] = Field(default_factory=list)
    # Search snippets never populate evidence. Official URLs must come from trusted provider records.
    official_urls: list[str] = Field(default_factory=list)


class EntityRelationship(Model):
    type: Literal["TAKES_PLACE_AT", "TICKETS_SOLD_BY", "RESOLVED_MERCHANT"]
    target_id: str
    evidence_ids: list[str]


class MerchantResolution(Model):
    status: Literal["MATCHED", "POSSIBLE_MATCH", "NO_MATCH"] = "NO_MATCH"
    merchant_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = "No corroborated merchant identity"


class AmexValueMatch(Model):
    source_id: str
    card_id: str
    title: str
    kind: Literal["OFFER", "BENEFIT", "REWARD"]
    amount: Decimal | None = None
    currency: str | None = None
    points: int = 0
    condition_ids: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    eligible: bool = False
    stackable: bool = False
    included: bool = False
    stacking_group: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source: str
    expires_at: datetime
    synthetic: Literal[True] = True
    label: str = "Demo / illustrative AMEX value"


class RealWorldEntity(Model):
    entity_id: str
    entity_type: Category
    canonical_name: str
    facts: dict[str, JsonValue]
    sources: list[FieldEvidence]
    conflicts: dict[str, list[str]] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    freshness: dict[str, str] = Field(default_factory=dict)
    verification_status: Literal["VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED"]
    relationships: list[EntityRelationship] = Field(default_factory=list)
    merchant: MerchantResolution = Field(default_factory=MerchantResolution)
    amex_matches: list[AmexValueMatch] = Field(default_factory=list)
    synthetic: bool = False


class RouteLeg(Model):
    origin_id: str
    destination_id: str
    duration_seconds: int = Field(ge=0)
    distance_meters: int = Field(ge=0)
    provider: str
    retrieved_at: datetime
    expires_at: datetime
    synthetic: bool = False

    @model_validator(mode="after")
    def valid_route(self):
        if self.retrieved_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Route timestamps must include a timezone")
        if self.expires_at <= self.retrieved_at:
            raise ValueError("Route expiry must follow retrieval")
        if not self.origin_id.strip() or not self.destination_id.strip() or not self.provider.strip():
            raise ValueError("Route endpoints and provider must not be blank")
        return self


class Stop(Model):
    entity: RealWorldEntity
    arrival: datetime
    departure: datetime
    duration_assumed: bool = True
    explanation: str
    evidence_ids: list[str]
    score: float

    @model_validator(mode="after")
    def ordered_visit(self):
        if self.arrival.tzinfo is None or self.departure.tzinfo is None:
            raise ValueError("Visit timestamps must include a timezone")
        if self.departure <= self.arrival:
            raise ValueError("Visit departure must follow arrival")
        return self


class Alternative(Model):
    stops: list[Stop]
    routes: list[RouteLeg]
    totals_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    reward_points: int = 0
    feasibility: Literal["CHECKED", "INCOMPLETE"] = "INCOMPLETE"


class OutingPlan(Model):
    outing_id: str
    status: Literal["READY", "PARTIAL", "ERROR"]
    mode: Literal["demo", "realtime"]
    search_plan: SearchPlan | None = None
    alternatives: list[Alternative] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime
    expires_at: datetime
    value_label: str = "Demo / illustrative AMEX value"
    hypothetical: bool = False

    @model_validator(mode="after")
    def valid_lifetime(self):
        if self.generated_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Outing timestamps must include a timezone")
        if self.expires_at <= self.generated_at:
            raise ValueError("Outing expiry must follow generation")
        return self


class PipelineEvent(Model):
    run_id: str
    sequence: int
    stage: str
    timestamp: datetime
    message: str
    result: OutingPlan | None = None


# Canonical route name without changing the existing wire contract.
Route = RouteLeg

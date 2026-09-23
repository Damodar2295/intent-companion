"""Strong domain contracts shared by services, storage and the API."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

Lifecycle = Literal["prospect", "member"]
IntentType = Literal["travel", "dining", "event", "shopping", "lifestyle"]
Preference = Literal["fine dining", "museums", "luxury hotels", "shopping", "dining", "culture"]
Category = Literal["travel", "dining", "hotel", "lounge", "entertainment", "shopping", "membership", "rewards"]
SignalType = Literal[
    "travel_search",
    "hotel_search",
    "travel_booking",
    "restaurant_search",
    "restaurant_booking",
    "ad_click",
    "website_interaction",
    "app_interaction",
    "customer_declared_intent",
    "event_search",
    "event_booking",
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Consent(Model):
    allowed: bool = False
    purpose: Literal["personalization"] = "personalization"


class SignalContext(Model):
    intent_type: IntentType | None = None
    origin: str | None = None
    destination: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    purpose: Literal["leisure", "business"] = "leisure"
    preferences: list[Preference] = Field(default_factory=list)

    @field_validator("destination")
    @classmethod
    def normalize_destination(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        cleaned = value.strip().casefold()
        return "Rome" if cleaned in {"rome", "roma", "fco"} else value.strip().title()

    @model_validator(mode="after")
    def date_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class IntentSignal(Model):
    event_id: str = Field(min_length=1, max_length=100)
    customer_id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    event_type: SignalType
    timestamp: datetime
    consent: Consent = Field(default_factory=Consent)
    context: SignalContext
    source_type: Literal["SYNTHETIC"] = "SYNTHETIC"
    synthetic: Literal[True] = True

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_type(cls, value):
        if isinstance(value, str):
            value = value.strip().lower().replace("-", "_").replace(" ", "_")
        return {
            "flight_search": "travel_search",
            "restaurant_reservation": "restaurant_booking",
            "declared_intent": "customer_declared_intent",
            "event_reservation": "event_booking",
        }.get(value, value)

    @field_validator("timestamp")
    @classmethod
    def aware_timestamp(cls, value):
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(UTC)


class CustomerContext(Model):
    customer_id: str
    display_name: str
    lifecycle_stage: Lifecycle
    existing_cards: list[str] = Field(default_factory=list)
    stated_preferences: list[Preference] = Field(default_factory=list)
    suppressed_preferences: list[Preference] = Field(default_factory=list)
    consent: Consent = Field(default_factory=Consent)
    market: str = "US"
    segment: str = "consumer"
    source_type: Literal["SYNTHETIC"] = "SYNTHETIC"
    synthetic: Literal[True] = True


class Evidence(Model):
    evidence_id: str = Field(min_length=1)
    type: Literal["signal", "intent", "preference", "catalog", "rule"]
    source_id: str = Field(min_length=1)
    fact: str = Field(min_length=1)
    weight: float | None = Field(default=None, ge=0, le=1)


class IntentContext(Model):
    intent_id: str
    customer_id: str
    intent_type: IntentType = "travel"
    destination: str
    start_date: date
    end_date: date
    purpose: str
    preferences: list[Preference]
    lifecycle_stage: Lifecycle
    intent_stage: Literal["exploring", "planning", "booked"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence]
    signal_ids: list[str]
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def valid_window(self):
        if self.end_date < self.start_date:
            raise ValueError("Intent end_date must not precede start_date")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Intent timestamps must include a timezone")
        if self.expires_at <= self.created_at:
            raise ValueError("Intent expiry must follow creation")
        return self


class CatalogBase(Model):
    item_id: str
    title: str
    description: str
    category: Category
    tags: list[Preference] = Field(default_factory=list)
    market: str = "US"
    segment: str = "consumer"
    geography: str = "Rome"
    valid_from: date
    valid_to: date
    last_verified: date
    source: str
    catalog_version: str = "synthetic-v1"
    source_type: Literal["SYNTHETIC"] = "SYNTHETIC"
    synthetic: Literal[True] = True
    conditions: list[str] = Field(default_factory=list)
    # Unknown stacking is never added to totals. Each explicit group is a separate
    # mock spending opportunity; alternatives within the group are mutually exclusive.
    stacking_group: str | None = None
    stackable: bool = False

    @model_validator(mode="after")
    def valid_catalog(self):
        if self.valid_to < self.valid_from:
            raise ValueError("Catalog valid_to must not precede valid_from")
        if not self.item_id.strip():
            raise ValueError("Catalog identity must not be blank")
        currency = getattr(self, "currency", None)
        if currency is not None and (
            len(currency) != 3 or not currency.isascii() or not currency.isupper() or not currency.isalpha()
        ):
            raise ValueError("Currency must be a three-letter uppercase code")
        return self


class CardProduct(CatalogBase):
    kind: Literal["card"] = "card"
    product_id: str
    product_name: str
    product_description: str
    product_categories: list[Category]
    product_rules: Literal["contextual_only"] = "contextual_only"


class Benefit(CatalogBase):
    kind: Literal["benefit"] = "benefit"
    benefit_id: str
    product_id: str
    subcategory: str
    eligibility_rule: Literal["held_product_or_prospect_illustration"] = "held_product_or_prospect_illustration"
    value_type: Literal["savings", "experiential"]
    value_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None


class Offer(CatalogBase):
    kind: Literal["offer"] = "offer"
    offer_id: str
    merchant_id: str
    location: str = "Rome"
    eligible_products: list[str]
    value_type: Literal["savings"] = "savings"
    value_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None


class MembershipRewardOpportunity(CatalogBase):
    kind: Literal["reward"] = "reward"
    reward_id: str
    product_id: str
    rule: Literal["mock_fixed_points"] = "mock_fixed_points"
    points: int = Field(ge=0)
    valuation_rule: Literal["points_times_mock_rate"] = "points_times_mock_rate"
    value_per_point: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None


class Merchant(CatalogBase):
    kind: Literal["merchant"] = "merchant"
    merchant_id: str
    name: str
    city: str = "Rome"
    accepting_products: list[str]


CatalogItem = Annotated[
    CardProduct | Benefit | Offer | MembershipRewardOpportunity | Merchant, Field(discriminator="kind")
]
CATALOG_ADAPTER = TypeAdapter(CatalogItem)


class ValueBreakdown(Model):
    source_id: str = Field(min_length=1)
    product_id: str
    value_type: Literal["savings", "rewards"]
    amount: Decimal
    currency: str
    calculation_rule: str
    assumptions: list[str]
    included_in_total: bool = False
    exclusion_reason: str | None = None


class ValueSummary(Model):
    product_id: str
    totals_by_currency: dict[str, Decimal]
    breakdown: list[ValueBreakdown]
    disclaimer: str = (
        "Synthetic potential value, not guaranteed savings. Alternatives are not additive; fees are not modeled."
    )


class Recommendation(Model):
    recommendation_id: str
    recommendation_type: Literal["card", "benefit", "offer", "reward", "merchant"]
    title: str
    description: str
    category: Category
    product_ids: list[str]
    relevance_score: float
    evidence: list[Evidence] = Field(min_length=1)
    value: list[ValueBreakdown] = Field(default_factory=list)
    source_ids: list[str] = Field(min_length=1)
    conditions: list[str]
    explanation: str


class TraceStep(Model):
    stage: str
    description: str
    count: int


class CompanionExperience(Model):
    experience_id: str
    customer_id: str
    lifecycle_stage: Lifecycle
    intent: IntentContext | None = None
    headline: str
    summary: str
    recommended_cards: list[Recommendation] = Field(default_factory=list)
    benefits: list[Recommendation] = Field(default_factory=list)
    offers: list[Recommendation] = Field(default_factory=list)
    rewards: list[Recommendation] = Field(default_factory=list)
    merchants: list[Recommendation] = Field(default_factory=list)
    value_summary: list[ValueSummary] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    preferences_used: list[Preference] = Field(default_factory=list)
    status: Literal["ready", "abstained"]
    abstention_reasons: list[str] = Field(default_factory=list)
    provider_mode: str = "deterministic"
    fallback_reason: str | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    source_type: Literal["SYNTHETIC"] = "SYNTHETIC"
    synthetic: Literal[True] = True
    generated_at: datetime


# Canonical spelling; retain the original import name and serialized fields.
RewardOpportunity = MembershipRewardOpportunity

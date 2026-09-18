"""Business contracts remain separate from consumer travel preferences."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from agent.domain import Consent, Model

SpendCategory = Literal["ingredients", "packaging", "equipment", "software", "travel", "employees"]
GoalType = Literal["expansion", "client_growth", "replenishment"]
SignalType = Literal["declared_goal", "supplier_search", "scheduled_payment", "spend_observation", "employee_growth"]


class BusinessContext(Model):
    business_id: str
    name: str
    industry: Literal["bakery", "consultancy"]
    market: str = "US"
    service_area: str = "US"
    held_products: list[str]
    priorities: list[SpendCategory]
    consent: Consent
    synthetic: Literal[True] = True


class SpendObservation(Model):
    observation_id: str = Field(min_length=1, max_length=100)
    category: SpendCategory
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: Literal["USD"] = "USD"
    payment_method: Literal["held_card", "other", "undecided"]
    status: Literal["observed", "planned"]
    period_start: date
    period_end: date
    observed_on: date

    @model_validator(mode="after")
    def dates(self):
        if self.period_end < self.period_start:
            raise ValueError("Spend period end must follow its start")
        return self


class BusinessSignal(Model):
    event_id: str = Field(min_length=1, max_length=100)
    business_id: str
    goal_id: str = Field(min_length=1, max_length=100)
    goal_type: GoalType
    event_type: SignalType
    timestamp: datetime
    consent: Consent
    category: SpendCategory | None = None
    spend: SpendObservation | None = None
    synthetic: Literal[True] = True

    @field_validator("timestamp")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Signal timestamp requires timezone")
        return value


class BusinessEvidence(Model):
    source_id: str
    origin: Literal["declared_goal", "observed_activity", "recurring_pattern", "scheduled_activity", "catalog", "rule"]
    fact: str
    weight: float = 0


class BusinessIntentContext(Model):
    intent_id: str
    business_id: str
    goal_id: str
    goal_type: GoalType
    intent_stage: Literal["exploring", "planning", "committed"]
    confidence: float
    confirmation: Literal["unconfirmed", "confirmed", "dismissed"] = "unconfirmed"
    categories: list[SpendCategory]
    signal_ids: list[str]
    evidence: list[BusinessEvidence]
    spend: list[SpendObservation]
    created_at: datetime
    expires_at: datetime


class CatalogRecord(Model):
    item_id: str
    name: str
    source: str
    market: str = "US"
    service_area: str = "US"
    valid_from: date
    valid_to: date
    last_verified: date
    version: str = "business-v1"
    synthetic: Literal[True] = True


class BusinessProduct(CatalogRecord):
    pass


class Supplier(CatalogRecord):
    category: SpendCategory
    accepting_products: list[str]


class BusinessOpportunity(CatalogRecord):
    category: SpendCategory
    industries: list[Literal["bakery", "consultancy"]]
    goal_types: list[GoalType]
    supplier_id: str
    product_ids: list[str]
    description: str
    rule: Literal["percent_savings", "points_per_dollar", "informational"]
    rate: Decimal | None = Field(default=None, ge=0)
    minimum_spend: Decimal = Field(default=Decimal(0), ge=0)
    cap: Decimal | None = Field(default=None, ge=0)
    point_value: Decimal | None = Field(default=None, ge=0)
    stacking_group: str | None = None
    conditions: list[str]


class BusinessValue(Model):
    source_id: str
    product_id: str
    observation_id: str
    amount: Decimal
    currency: str = "USD"
    value_type: Literal["savings", "rewards"]
    points: Decimal | None = None
    calculation_rule: str
    period: str
    assumptions: list[str]
    included_in_total: bool = False
    exclusion_reason: str | None = None


class BusinessRecommendation(Model):
    recommendation_id: str
    title: str
    description: str
    category: SpendCategory
    supplier: str
    supplier_id: str
    product_ids: list[str]
    evidence: list[BusinessEvidence]
    conditions: list[str]
    values: list[BusinessValue] = Field(default_factory=list)
    value_note: str | None = None
    score: float


class BusinessExperience(Model):
    experience_id: str
    business_id: str
    status: Literal["ready", "abstained"]
    intent: BusinessIntentContext | None = None
    recommendations: list[BusinessRecommendation] = Field(default_factory=list)
    products: list[BusinessProduct] = Field(default_factory=list)
    spend_summary: dict[str, Decimal] = Field(default_factory=dict)
    totals_by_product: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    abstention_reasons: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    provider_mode: str = "deterministic"
    trace: list[str] = Field(default_factory=list)


class BusinessScenario(Model):
    scenario_id: str
    business_id: str
    goal_id: str
    title: str
    subtitle: str
    goal_text: str
    signal_ids: list[str]
    default_priorities: list[SpendCategory]


class BusinessFixtures(Model):
    businesses: list[BusinessContext]
    scenarios: list[BusinessScenario]
    products: list[BusinessProduct]
    suppliers: list[Supplier]
    opportunities: list[BusinessOpportunity]
    signals: list[BusinessSignal]

    @model_validator(mode="after")
    def references(self):
        groups = [
            (self.businesses, "business_id"),
            (self.products, "item_id"),
            (self.suppliers, "item_id"),
            (self.opportunities, "item_id"),
            (self.signals, "event_id"),
            (self.scenarios, "scenario_id"),
        ]
        for records, key in groups:
            ids = [getattr(r, key) for r in records]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate {key} in business fixture")
        products = {p.item_id for p in self.products}
        suppliers = {s.item_id for s in self.suppliers}
        businesses = {b.business_id for b in self.businesses}
        signals = {s.event_id: s for s in self.signals}
        for item in self.opportunities:
            if item.supplier_id not in suppliers or not set(item.product_ids) <= products:
                raise ValueError(f"Opportunity {item.item_id} has an unknown supplier/product")
        for scenario in self.scenarios:
            if scenario.business_id not in businesses or any(
                i not in signals
                or signals[i].business_id != scenario.business_id
                or signals[i].goal_id != scenario.goal_id
                for i in scenario.signal_ids
            ):
                raise ValueError(f"Scenario {scenario.scenario_id} has invalid owner/goal/signal references")
        return self

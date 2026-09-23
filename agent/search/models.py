from datetime import date as Date
from datetime import time
from decimal import Decimal
from typing import Literal

from pydantic import Field

from agent.domain import Consent, Model
from agent.outing.models import Category, Location, SearchPlan

Task = Literal["OUTING_PLANNING", "BENEFIT_LOOKUP"]


class SearchPlanRequest(Model):
    customer_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=3, max_length=1500)
    consent: Consent = Field(default_factory=Consent)
    intent_id: str | None = None
    task: Task | None = None
    city: str | None = Field(default=None, min_length=1, max_length=100)
    date: Date | None = None
    timezone: str | None = None
    start_time: time | None = None
    end_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=720)
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    travel_mode: Literal["WALK", "DRIVE", "TRANSIT"] | None = None
    user_location: Location | None = None
    number_of_people: int = Field(default=1, ge=1, le=12)
    include_amex_value: bool | None = None


class CategoryQuote(Model):
    category: Category
    quote: str = Field(min_length=1, max_length=100)


class PlanInterpretation(Model):
    task: Task
    categories: list[CategoryQuote] = Field(max_length=6)
    destination_quote: str | None = Field(max_length=100)
    date_quote: str | None = Field(max_length=100)
    start_time_quote: str | None = Field(max_length=30)
    end_time_quote: str | None = Field(max_length=30)
    duration_quote: str | None = Field(max_length=30)
    budget_quote: str | None = Field(max_length=50)
    transport_quote: str | None = Field(max_length=30)
    location_quote: str | None = Field(max_length=30)
    value_quote: str | None = Field(max_length=30)
    clarification: str | None = Field(max_length=200)


class InputEvidence(Model):
    field: str
    quote: str


class SearchRequirements(Model):
    task: Task
    categories: list[Category] = Field(min_length=1, max_length=6)
    preferences: list[str] = Field(max_length=12)
    destination: str | None = None
    outing: SearchPlan | None = None
    requires_real_world_discovery: bool
    requires_routing: bool
    requires_amex_value: bool
    origin_reference: Literal["UNSPECIFIED", "PROVIDED", "NEAR_HOTEL", "NEAR_ME"]
    assumptions: list[str] = Field(default_factory=list)
    evidence: list[InputEvidence] = Field(default_factory=list)


class SearchPlanResponse(Model):
    status: Literal["READY", "CLARIFICATION_REQUIRED"]
    search_plan: SearchRequirements | None = None
    clarification_fields: list[str] = Field(default_factory=list)
    message: str
    provider_mode: Literal["mock", "llm"]

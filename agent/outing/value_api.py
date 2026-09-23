from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import Field

from agent.domain import Consent, Model
from agent.outing.models import OutingRequest, RealWorldEntity
from agent.outing.value import enrich, resolve


class ValuePreviewRequest(Model):
    customer_id: str = Field(min_length=1, max_length=100)
    consent: Consent = Field(default_factory=Consent)
    entity: RealWorldEntity
    card_id: str = Field(min_length=1, max_length=100)
    date: date
    confirmed_condition_ids: list[str] = Field(default_factory=list, max_length=30)


def value_routes(app):
    router = APIRouter(prefix="/api/v1/value", tags=["AMEX value v1"])

    @router.post("/preview")
    async def preview(body: ValuePreviewRequest):
        customer = app.state.repository.customer(body.customer_id)
        if not customer.consent.allowed or not body.consent.allowed:
            raise HTTPException(403, "Personalization consent is missing or withdrawn.")
        if (
            customer.segment == "consumer"
            and customer.lifecycle_stage == "member"
            and body.card_id not in customer.existing_cards
        ):
            raise HTTPException(403, "Selected card is not held by this member.")
        entity = body.entity.model_copy(deep=True)
        entity.merchant = resolve(entity, app.state.outing.settings.merchant_mappings)
        request = OutingRequest(
            customer_id=body.customer_id,
            text="value preview",
            date=body.date,
            card_id=body.card_id,
            confirmed_condition_ids=body.confirmed_condition_ids,
        )
        catalog = app.state.outing.catalog.catalog(customer.market, customer.segment, entity.facts.get("city", "Rome"))
        enrich(
            entity,
            catalog,
            body.card_id,
            request,
            app.state.outing.settings.now(),
            app.state.outing.settings.catalog_refresh_days,
        )
        return {
            "merchant": entity.merchant,
            "matches": entity.amex_matches,
            "label": "Demo / illustrative AMEX value",
            "eligibility_evaluated": False,
            "currency_conversion": False,
            "points_separate": True,
        }

    return router

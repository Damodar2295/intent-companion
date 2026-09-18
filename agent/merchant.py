"""QR codes identify merchants only; catalog records establish acceptance and offers."""

from datetime import timedelta
from typing import Literal

from agent.business.matching import fresh
from agent.business.models import BusinessOpportunity, BusinessProduct, Supplier
from agent.domain import CardProduct, Merchant, Model, Offer
from agent.repositories import Abstain


class MerchantRequest(Model):
    owner_type: Literal["consumer", "business"]
    owner_id: str
    code: str


def resolve(request, repository, store, settings):
    examples = {
        "consumer": {"DEMO-DINING": "merchant-01", "DEMO-NO-OFFER": "merchant-06", "DEMO-UNKNOWN": "unknown"},
        "business": {
            "DEMO-PACKAGING": "supplier-packaging",
            "DEMO-NO-OFFER": "supplier-employees",
            "DEMO-UNKNOWN": "supplier-stale",
        },
    }
    code = examples[request.owner_type].get(request.code.strip().upper(), request.code.strip())
    if request.owner_type == "business":
        owner = store.business(request.owner_id)
        if not owner.consent.allowed:
            raise Abstain("Personalization consent is missing or withdrawn.")
        records = [Supplier.model_validate(s) for s in store.all("supplier")]
        merchant = next(
            (
                s
                for s in records
                if s.item_id == code
                and s.market == owner.market
                and s.service_area == owner.service_area
                and fresh(s, settings)
            ),
            None,
        )
        products = {
            p.item_id: p
            for raw in store.all("product")
            if fresh(p := BusinessProduct.model_validate(raw), settings)
            and p.item_id in owner.held_products
            and p.market == owner.market
        }
        accepted = sorted(set(merchant.accepting_products) & set(products)) if merchant else []
        offers = [
            o
            for raw in store.all("opportunity")
            if fresh(o := BusinessOpportunity.model_validate(raw), settings)
            and o.supplier_id == code
            and o.rule == "percent_savings"
            and o.rate is not None
            and owner.industry in o.industries
            and o.market == owner.market
            and set(o.product_ids) & set(accepted)
        ]
        names = [o.name for o in offers]
    else:
        owner = repository.customer(request.owner_id)
        if not owner.consent.allowed:
            raise Abstain("Personalization consent is missing or withdrawn.")
        records = repository.catalog(owner.market, owner.segment, "Rome")

        def current(item):
            today = settings.now().date()
            return bool(
                item.source
                and item.valid_from <= today <= item.valid_to
                and today - timedelta(days=settings.catalog_ttl_days) <= item.last_verified <= today
            )

        merchant = next((s for s in records if isinstance(s, Merchant) and s.item_id == code and current(s)), None)
        products = {
            p.product_id: p
            for p in records
            if isinstance(p, CardProduct) and current(p) and p.product_id in owner.existing_cards
        }
        accepted = sorted(set(merchant.accepting_products) & set(products)) if merchant else []
        offers = [
            o
            for o in records
            if isinstance(o, Offer)
            and current(o)
            and o.merchant_id == code
            and o.location == "Rome"
            and o.value_amount is not None
            and o.currency
            and set(o.eligible_products) & set(accepted)
        ]
        names = [o.title for o in offers]
    return {
        "status": "verified" if merchant else "unknown",
        "merchant_name": (getattr(merchant, "name", "") if merchant else "Unable to verify this merchant"),
        "accepted_products": [
            {"id": p, "name": getattr(products[p], "name", getattr(products[p], "title", p))} for p in accepted
        ],
        "offers": [{"id": o.item_id, "title": name, "conditions": o.conditions} for o, name in zip(offers, names)]
        if merchant
        else [],
        "source": merchant.source if merchant else None,
        "last_verified": str(merchant.last_verified) if merchant else None,
        "message": "Acceptance is verified independently from offers. Offer conditions still apply."
        if merchant
        else "Acceptance is unknown, not a rejection. No offer claim can be made.",
    }

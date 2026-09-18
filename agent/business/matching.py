"""Business matching uses authoritative structured relationships before ranking."""

from datetime import timedelta

from agent.business.models import (
    BusinessEvidence,
    BusinessOpportunity,
    BusinessProduct,
    BusinessRecommendation,
    Supplier,
)
from agent.repositories import Abstain


def fresh(item, settings):
    today = settings.now().date()
    return bool(
        item.source
        and item.valid_from <= today <= item.valid_to
        and today - timedelta(days=settings.catalog_ttl_days) <= item.last_verified <= today
    )


def match(store, settings, customer, intent):
    products = {
        p.item_id: p
        for raw in store.all("product")
        if fresh(p := BusinessProduct.model_validate(raw), settings)
        and p.market == customer.market
        and p.service_area == customer.service_area
        and p.item_id in customer.held_products
    }
    if set(products) != set(customer.held_products) or not products:
        raise Abstain("A held business card is unavailable or stale.")
    suppliers = {
        s.item_id: s
        for raw in store.all("supplier")
        if fresh(s := Supplier.model_validate(raw), settings)
        and s.market == customer.market
        and s.service_area == customer.service_area
    }
    result, items, exclusions = [], {}, []
    for raw in store.all("opportunity"):
        item = BusinessOpportunity.model_validate(raw)
        if (
            item.category not in intent.categories
            or customer.industry not in item.industries
            or intent.goal_type not in item.goal_types
        ):
            continue
        supplier = suppliers.get(item.supplier_id)
        if (
            not fresh(item, settings)
            or item.market != customer.market
            or item.service_area != customer.service_area
            or not supplier
            or supplier.category != item.category
        ):
            exclusions.append(f"{item.item_id}: freshness, service area or supplier verification failed.")
            continue
        allowed = sorted(set(item.product_ids) & set(products) & set(supplier.accepting_products))
        if not allowed:
            exclusions.append(f"{item.item_id}: no held, accepted product.")
            continue
        evidence = [e for e in intent.evidence if e.origin == "declared_goal" or item.category in e.fact]
        evidence += [
            BusinessEvidence(
                source_id=r.item_id,
                origin="catalog",
                fact=f"{r.name}; {r.source}; verified {r.last_verified}; {r.version}.",
            )
            for r in [item, supplier, *[products[p] for p in allowed]]
        ]
        evidence.append(
            BusinessEvidence(
                source_id=item.item_id,
                origin="rule",
                fact=f"Matched active priority {item.category}; industry, goal, held card, supplier acceptance, geography and freshness passed.",
            )
        )
        result.append(
            BusinessRecommendation(
                recommendation_id=item.item_id,
                title=item.name,
                description=item.description,
                category=item.category,
                supplier=supplier.name,
                supplier_id=supplier.item_id,
                product_ids=allowed,
                evidence=evidence,
                conditions=item.conditions,
                score=0.8,
            )
        )
        items[item.item_id] = item
    if not result:
        raise Abstain("No verified business opportunity matches the current goal and priorities.")
    return result, items, list(products.values()), exclusions

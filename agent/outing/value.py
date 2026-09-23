"""Branch identity and conservative outing-only catalog calculations."""

import json
import re
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from agent.outing.models import AmexValueMatch, FieldEvidence, MerchantResolution


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def resolve(entity, mappings=()):
    # Synthetic IDs are valid only for synthetic entities, never a name-based bridge to live merchants.
    if entity.synthetic and entity.entity_type != "EVENT" and entity.facts.get("demo_merchant_id"):
        return MerchantResolution(
            status="MATCHED",
            merchant_id=entity.facts["demo_merchant_id"],
            evidence_ids=[e.evidence_id for e in entity.sources if e.field == "demo_merchant_id"],
            reason="Exact fixture merchant identifier; illustrative identity only",
        )
    if entity.entity_type == "EVENT":
        return MerchantResolution(reason="Event, venue and ticket seller identities are separate")
    for mapping in mappings:
        ids = [e.evidence_id for e in entity.sources if e.field in {"place_id", "address", "name", "website"}]
        trusted = mapping.get("place_id") and mapping["place_id"] == entity.facts.get("place_id")
        branch = (
            normalized(entity.canonical_name) in [normalized(n) for n in mapping.get("names", [])]
            and normalized(str(entity.facts.get("address", ""))) == normalized(mapping.get("address", ""))
            and bool(mapping.get("address"))
            and entity.facts.get("website") == mapping.get("website")
            and bool(mapping.get("website"))
        )
        if trusted or branch:
            return MerchantResolution(
                status="MATCHED",
                merchant_id=mapping["merchant_id"],
                evidence_ids=ids,
                reason="Trusted branch identity mapping",
            )
    return MerchantResolution()


DEMO_ITEM_MAPPINGS = json.loads((Path(__file__).parent / "fixtures/merchant_mappings.json").read_text())


def enrich(entity, catalog, card_id, request, now, refresh_days=30):
    if entity.merchant.status != "MATCHED" or not card_id:
        return
    for item in catalog:
        merchant_match = getattr(item, "merchant_id", None) == entity.merchant.merchant_id
        fixture_match = entity.synthetic and item.item_id in DEMO_ITEM_MAPPINGS.get(entity.merchant.merchant_id, [])
        products = getattr(item, "eligible_products", [getattr(item, "product_id", None)])
        if (
            not (merchant_match or fixture_match)
            or item.kind not in {"offer", "benefit", "reward"}
            or card_id not in products
            or not item.valid_from <= request.date <= item.valid_to
        ):
            continue
        # Existing catalog has a fixed verification date, not a live AMEX refresh.
        expiry = min(
            datetime.combine(item.valid_to + timedelta(days=1), time(), UTC),
            datetime.combine(item.last_verified, time(), UTC) + timedelta(days=refresh_days),
        )
        if now >= expiry:
            continue
        conditions = [f"{item.item_id}:{i}" for i in range(len(item.conditions))]
        eligible = all(c in request.confirmed_condition_ids for c in conditions)
        evidence_id = f"amex:{item.item_id}:{card_id}"
        entity.sources.append(
            FieldEvidence(
                evidence_id=evidence_id,
                field=f"amex.{item.item_id}",
                value={
                    "amount": str(getattr(item, "value_amount", None)),
                    "currency": getattr(item, "currency", None),
                    "points": getattr(item, "points", 0),
                    "conditions": item.conditions,
                    "card_id": card_id,
                },
                source_type="DEMO",
                url=item.source,
                provider="synthetic_amex",
                retrieved_at=datetime.combine(item.last_verified, time(), UTC),
                expires_at=expiry,
                confidence=0.95,
                synthetic=True,
                attribution="Demo / illustrative AMEX value",
            )
        )
        entity.amex_matches.append(
            AmexValueMatch(
                source_id=item.item_id,
                card_id=card_id,
                title=item.title,
                kind=item.kind.upper(),
                amount=getattr(item, "value_amount", None),
                currency=getattr(item, "currency", None),
                points=getattr(item, "points", 0),
                condition_ids=conditions,
                conditions=item.conditions,
                eligible=eligible,
                stackable=item.stackable,
                stacking_group=getattr(item, "stacking_group", None) or "exclusive",
                source=item.source,
                expires_at=expiry,
                evidence_ids=[*entity.merchant.evidence_ids, evidence_id],
            )
        )


def aggregate(stops):
    """One selected value per explicit stacking group; points are never compared with money."""
    groups, seen = {}, set()
    for stop in stops:
        for match in stop.entity.amex_matches:
            match.included = False
            if not match.eligible or not match.stackable or not match.stacking_group or match.source_id in seen:
                continue
            seen.add(match.source_id)
            groups.setdefault((match.card_id, match.stacking_group), []).append(match)
    totals, points, chosen = {}, 0, set()
    for items in groups.values():
        cash = [m for m in items if m.kind != "REWARD" and m.amount is not None and m.currency]
        if cash:
            # Different currencies in the same exclusive group cannot be compared without an FX assumption.
            if len({m.currency for m in cash}) != 1:
                continue
            match = min(cash, key=lambda m: (-m.amount, m.source_id))
            totals[match.currency] = totals.get(match.currency, Decimal(0)) + match.amount
            chosen.add(match.source_id)
        else:
            rewards = [m for m in items if m.kind == "REWARD"]
            if rewards:
                match = min(rewards, key=lambda m: (-m.points, m.source_id))
                points += match.points
                chosen.add(match.source_id)
    for stop in stops:
        for match in stop.entity.amex_matches:
            match.included = match.source_id in chosen
    return totals, points

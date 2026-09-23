"""Validated seed input for later ingestion. Never queried by customer runtime."""

import json
from pathlib import Path

from pydantic import Field, model_validator

from agent.canonical.models import AmexExperience, Event, Place, Source
from agent.domain import CATALOG_ADAPTER, CustomerContext, Evidence, IntentSignal, Model


class KnowledgeSeeds(Model):
    sources: list[Source] = Field(min_length=1)
    places: list[Place] = Field(min_length=1)
    events: list[Event] = Field(min_length=1)
    experiences: list[AmexExperience] = Field(min_length=1)
    relationship_evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def references(self):
        def indexed(items, key):
            index = {getattr(item, key): item for item in items}
            if len(index) != len(items):
                raise ValueError(f"Duplicate {key} in seeds")
            return index

        sources = indexed(self.sources, "source_id")
        places = indexed(self.places, "place_id")
        events = indexed(self.events, "event_id")
        indexed(self.experiences, "experience_id")
        evidence = indexed(self.relationship_evidence, "evidence_id")
        for item in [*self.sources, *self.places, *self.events, *self.experiences]:
            if item.source_type != "SYNTHETIC":
                raise ValueError("Seed inventory must be explicitly SYNTHETIC")
        for item in [*self.places, *self.events, *self.experiences]:
            if any(key not in sources for key in item.source_ids):
                raise ValueError("Unknown source reference")
        for event in self.events:
            if event.venue_id not in places:
                raise ValueError("Unknown event venue")
            venue = places[event.venue_id]
            if (event.city, event.country) != (venue.city, venue.country):
                raise ValueError("Event and venue geography disagree")
        for proof in evidence.values():
            if proof.source_id not in sources:
                raise ValueError("Unknown relationship evidence source")
        for experience in self.experiences:
            if experience.event_id and experience.event_id not in events:
                raise ValueError("Unknown experience event")
            if experience.venue_id and experience.venue_id not in places:
                raise ValueError("Unknown experience venue")
            if (
                experience.event_id
                and experience.venue_id
                and events[experience.event_id].venue_id != experience.venue_id
            ):
                raise ValueError("Experience event and venue disagree")
            if any(key not in evidence for key in experience.relationship_evidence_ids):
                raise ValueError("Unknown experience relationship evidence")
        return self


def validate_seed_directory(directory: Path) -> dict[str, int]:
    """Check legacy and new seeds together, including cross-domain references."""
    counts = {}
    catalog = []
    for kind in ("cards", "benefits", "offers", "rewards", "merchants"):
        rows = json.loads((directory / f"{kind}.json").read_text())
        if any(row.get("source_type") != "SYNTHETIC" for row in rows):
            raise ValueError("Catalog seed requires explicit SYNTHETIC source_type")
        catalog.extend(CATALOG_ADAPTER.validate_python(row) for row in rows)
        counts[kind] = len(rows)
    if len({item.item_id for item in catalog}) != len(catalog):
        raise ValueError("Duplicate catalog item identity")
    products = {item.product_id for item in catalog if item.kind == "card"}
    merchants = {item.merchant_id for item in catalog if item.kind == "merchant"}
    for item in catalog:
        if not item.source.strip():
            raise ValueError("Catalog seed requires a source")
        if (
            getattr(item, "value_amount", None) is not None or getattr(item, "value_per_point", None) is not None
        ) and not getattr(item, "currency", None):
            raise ValueError("Monetary seed values require a currency")
        if item.kind in {"benefit", "reward"} and item.product_id not in products:
            raise ValueError("Unknown catalog product")
        if item.kind == "offer" and item.merchant_id not in merchants:
            raise ValueError("Unknown offer merchant")
        references = getattr(item, "eligible_products", getattr(item, "accepting_products", []))
        if not set(references) <= products:
            raise ValueError("Unknown eligible product")
    customers = [CustomerContext.model_validate(row) for row in json.loads((directory / "customers.json").read_text())]
    signals = [IntentSignal.model_validate(row) for row in json.loads((directory / "signals.json").read_text())]
    customer_ids = {item.customer_id for item in customers}
    if len(customer_ids) != len(customers) or len({s.event_id for s in signals}) != len(signals):
        raise ValueError("Duplicate customer or signal identity")
    if any(s.customer_id not in customer_ids for s in signals):
        raise ValueError("Unknown signal customer")
    if any(not set(c.existing_cards) <= products for c in customers):
        raise ValueError("Unknown customer card")
    seeds = KnowledgeSeeds.model_validate_json((directory / "knowledge.json").read_text())
    if any(not set(e.eligible_product_ids) <= products for e in seeds.experiences):
        raise ValueError("Unknown experience product")
    if any(p.merchant_id and p.merchant_id not in merchants for p in seeds.places):
        raise ValueError("Unknown place merchant")
    counts.update(customers=len(customers), signals=len(signals))
    counts.update({name: len(getattr(seeds, name)) for name in ("sources", "places", "events", "experiences")})
    return counts

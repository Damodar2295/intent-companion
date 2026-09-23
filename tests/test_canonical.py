import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agent.canonical import (
    AmexExperience,
    Event,
    RewardOpportunity,
    Route,
    Source,
)
from agent.canonical.seeds import KnowledgeSeeds, validate_seed_directory
from agent.domain import CATALOG_ADAPTER, MembershipRewardOpportunity
from agent.outing.models import Location, RouteLeg, SearchPlan
from config.settings import ROOT


@pytest.fixture
def seeds():
    return json.loads((ROOT / "data/knowledge.json").read_text())


def test_seed_directory_and_roundtrip(seeds):
    counts = validate_seed_directory(ROOT / "data")
    assert counts["events"] == 6 and counts["experiences"] == 3
    bundle = KnowledgeSeeds.model_validate(seeds)
    assert KnowledgeSeeds.model_validate_json(bundle.model_dump_json()) == bundle
    for group in (bundle.sources, bundle.places, bundle.events, bundle.experiences):
        assert all(item.source_type == "SYNTHETIC" for item in group)
    assert len({p.place_id for p in bundle.places}) == 3
    assert len({p.name for p in bundle.places}) == 1
    assert len({p.city for p in bundle.places}) == 3
    assert len({e.event_id for e in bundle.events}) == 6
    assert len({e.starts_at for e in bundle.events}) == 2
    assert all(e.price is None and e.availability == "UNKNOWN" for e in bundle.events)


def test_canonical_aliases_preserve_wire_contract():
    assert RewardOpportunity is MembershipRewardOpportunity
    assert Route is RouteLeg


@pytest.mark.parametrize(
    "change",
    [
        {"ends_at": "2026-10-02T17:00:00+02:00"},
        {"starts_at": "2026-10-02T18:00:00"},
        {"timezone": "not/a-zone"},
        {"starts_at": "2026-10-02T18:00:00-05:00"},
        {"price": "10.00"},
        {"price": "-1", "currency": "EUR"},
        {"price": "NaN", "currency": "EUR"},
        {"currency": "USD"},
        {"price": "10", "currency": "eur"},
        {"event_id": " "},
        {"source_ids": []},
        {"invented_discount": 10},
    ],
)
def test_event_rejects_invalid_facts(seeds, change):
    with pytest.raises(ValidationError):
        Event.model_validate(seeds["events"][0] | change)


def test_decimal_price_roundtrip(seeds):
    event = Event.model_validate(seeds["events"][0] | {"price": "12.34", "currency": "EUR"})
    assert Event.model_validate_json(event.model_dump_json()).price == Decimal("12.34")


@pytest.mark.parametrize(
    "change",
    [
        {"expires_at": "2026-09-16T00:00:00Z"},
        {"retrieved_at": "2026-09-17T12:00:00"},
        {"verified_at": "2026-09-18T00:00:00"},
        {"verified_at": "2026-09-16T00:00:00Z"},
        {"url": "https://example.org/", "source_type": "DISCOVERY"},
        {"url": "https://example.org/"},
        {"source_type": "OFFICIAL", "url": "https://user:secret@example.org"},
    ],
)
def test_source_rejects_bad_provenance(seeds, change):
    with pytest.raises(ValidationError):
        Source.model_validate(seeds["sources"][0] | change)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x["events"][0].update(venue_id="missing"),
        lambda x: x["events"][0].update(source_ids=["missing"]),
        lambda x: x["events"][0].update(city="London"),
        lambda x: x["events"].append(deepcopy(x["events"][0])),
        lambda x: x["experiences"][0].update(relationship_evidence_ids=["missing"]),
        lambda x: x["experiences"][0].update(venue_id="seed-venue-1"),
        lambda x: x["places"][0].update(source_type="OFFICIAL"),
    ],
)
def test_seed_reference_integrity(seeds, mutation):
    mutation(seeds)
    with pytest.raises(ValidationError):
        KnowledgeSeeds.model_validate(seeds)


def test_experience_is_not_venue_inferred(seeds):
    value = seeds["experiences"][0] | {"relationship_evidence_ids": []}
    with pytest.raises(ValidationError):
        AmexExperience.model_validate(value)


def test_route_freshness_and_finite_coordinates():
    now = datetime.now(UTC)
    route = {
        "origin_id": "a",
        "destination_id": "b",
        "duration_seconds": 5,
        "distance_meters": 10,
        "provider": "demo",
        "retrieved_at": now,
        "expires_at": now + timedelta(minutes=5),
    }
    assert Route(**route).duration_seconds == 5
    for change in ({"expires_at": now}, {"retrieved_at": now.replace(tzinfo=None)}, {"distance_meters": -1}):
        with pytest.raises(ValidationError):
            Route(**(route | change))
    with pytest.raises(ValidationError):
        Location(lat=float("nan"), lng=12)


def test_invalid_catalog_dates_and_legacy_partial_record():
    row = json.loads((ROOT / "data/benefits.json").read_text())[0]
    with pytest.raises(ValidationError):
        CATALOG_ADAPTER.validate_python(row | {"valid_to": "2020-01-01"})
    # Legacy partial records remain parseable so deterministic matching can exclude them safely.
    assert CATALOG_ADAPTER.validate_python(row | {"currency": None, "source": ""}).currency is None


def test_searchplan_currency_and_timezone_validation():
    base = {"city": "Rome", "date": "2026-10-02", "timezone": "Europe/Rome", "categories": ["DINING"]}
    assert SearchPlan(**base).currency == "EUR"
    with pytest.raises(ValidationError):
        SearchPlan(**base, currency="euros")


def test_intent_validity_contract(service, repository):
    from agent.domain import IntentContext

    intent = service.intent_engine.detect("cust-dining")
    data = intent.model_dump()
    for change in (
        {"end_date": "2020-01-01"},
        {"expires_at": intent.created_at},
        {"created_at": intent.created_at.replace(tzinfo=None)},
        {"confidence": 1.1},
    ):
        with pytest.raises(ValidationError):
            IntentContext.model_validate(data | change)


def test_outing_lifetime_rejected():
    from agent.canonical import OutingPlan

    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        OutingPlan(outing_id="test", status="ERROR", mode="demo", generated_at=now, expires_at=now)

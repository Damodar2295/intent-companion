import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from agent.outing.config import OutingSettings
from agent.outing.demo import Demo
from agent.outing.live import Places, Routes
from agent.outing.models import AmexValueMatch, OutingRequest
from agent.outing.official import JSONLDParser, public_url
from agent.outing.planning import is_open
from agent.outing.providers import ProviderError, Transport
from agent.outing.service import OutingService
from agent.outing.value import aggregate, resolve
from agent.outing.verification import VerificationService, deduplicate


@pytest.fixture
def request_body():
    return OutingRequest(
        customer_id="cust-dining", text="event dining shopping", city="Rome", date=date(2026, 10, 2), card_id="card-a"
    )


@pytest.fixture
def outing_settings():
    class ClockSettings(OutingSettings):
        def now(self):
            return datetime(2026, 9, 21, 12, tzinfo=UTC)

    return ClockSettings()


async def test_rome_complete_with_evidence_and_no_unconfirmed_value(repository, outing_settings, request_body):
    service = OutingService(repository, outing_settings)
    try:
        events = [e async for e in service.stream(request_body)]
        result = events[-1].result
        assert result.status == "PARTIAL"  # prices not asserted by fixtures
        assert len(result.alternatives) == 3
        assert {s.entity.entity_type for s in result.alternatives[0].stops} == {"DINING", "SHOPPING", "EVENT"}
        assert all(s.evidence_ids for a in result.alternatives for s in a.stops)
        assert result.alternatives[0].totals_by_currency == {}
        assert all(r.synthetic for a in result.alternatives for r in a.routes)
        assert [e.sequence for e in events] == list(range(1, len(events) + 1))
        assert service.store.get(result.outing_id)
        customer = repository.customer(request_body.customer_id)
        customer.consent.allowed = False
        repository.save_customer(customer)
        assert service.store.get(result.outing_id) is None
    finally:
        await service.close()


async def test_conflicting_and_stale_fields_suppressed(outing_settings, request_body):
    demo = Demo(outing_settings)
    plan = await demo.interpret(request_body, [])
    candidate = (await demo.search(plan))[-1]
    start = next(e for e in candidate.evidence if e.field == "schedule.start")
    candidate.evidence.append(
        start.model_copy(update={"evidence_id": "conflict", "value": "2026-10-03T20:00:00+02:00"})
    )
    entity = VerificationService(outing_settings).verify(candidate)
    assert "schedule.start" not in entity.facts
    assert entity.verification_status == "UNVERIFIED"
    for e in candidate.evidence:
        if e.field == "opening_hours":
            e.retrieved_at = outing_settings.now() - timedelta(hours=7)
            e.expires_at = outing_settings.now() - timedelta(seconds=1)
    entity = VerificationService(outing_settings).verify(candidate)
    assert "opening_hours" not in entity.facts
    assert entity.freshness["opening_hours"] == "STALE"


async def test_same_names_never_merge_branches_or_event_dates(outing_settings, request_body):
    demo = Demo(outing_settings)
    candidate = (await demo.search(await demo.interpret(request_body, [])))[0]
    other = candidate.model_copy(update={"candidate_id": "other-branch"})
    assert len(deduplicate([candidate, candidate, other])) == 2


async def test_identity_requires_branch_evidence(outing_settings, request_body):
    demo = Demo(outing_settings)
    entity = VerificationService(outing_settings).verify((await demo.search(await demo.interpret(request_body, [])))[0])
    entity.synthetic = False
    entity.canonical_name = "Hotel Eden Rome"
    mapping = {
        "merchant_id": "real-eden",
        "names": ["Hotel Eden Rome", "Hotel Eden - Roma"],
        "address": "10 Rome",
        "website": "https://eden.example",
    }
    assert resolve(entity, [mapping]).status == "NO_MATCH"
    entity.facts.update(address="10 Rome", website="https://eden.example")
    assert resolve(entity, [mapping]).status == "MATCHED"
    entity.entity_type = "EVENT"
    assert resolve(entity, [mapping]).status == "NO_MATCH"


async def test_no_live_synthetic_fallback(repository, request_body):
    service = OutingService(repository, OutingSettings(demo=False, realtime=True))
    try:
        events = [e async for e in service.stream(request_body)]
        assert events[-1].result.status == "ERROR"
        assert "OPENAI_MODEL" in events[-1].result.warnings[0]
        assert events[-1].result.alternatives == []
    finally:
        await service.close()


async def test_route_failure_partial_without_fabricated_travel(repository, outing_settings, request_body):
    service = OutingService(repository, outing_settings)
    service.router = type("Fail", (), {"route": AsyncMock(side_effect=ProviderError("Routing unavailable"))})()
    try:
        result = [e async for e in service.stream(request_body)][-1].result
        assert result.status == "PARTIAL"
        assert all(len(a.stops) == 1 and not a.routes for a in result.alternatives)
    finally:
        await service.close()


async def test_provider_transient_retries_and_places_not_cached(outing_settings, request_body):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": "branch",
                        "displayName": {"text": "Verified name"},
                        "formattedAddress": "Address",
                        "location": {"latitude": 41.9, "longitude": 12.4},
                    }
                ]
            },
        )

    settings = outing_settings.model_copy(update={"places_key": "test"})
    transport = Transport(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        plan = await Demo(settings).interpret(request_body.model_copy(update={"text": "dining"}), [])
        places = await Places(transport, settings).search(plan)
        assert len(calls) == 3
        assert places[0].evidence and not transport.cache
    finally:
        await transport.close()


async def test_route_cache_preserves_correct_ids(outing_settings):
    from agent.outing.models import Location

    transport = Transport(
        outing_settings,
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"routes": [{"duration": "123s", "distanceMeters": 234}]})
            )
        ),
    )
    settings = outing_settings.model_copy(update={"routing_key": "test"})
    routes = Routes(transport, settings)
    a, b = Location(lat=41.9, lng=12.4), Location(lat=41.8, lng=12.3)
    try:
        first = await routes.route(a, b, settings.now(), "WALK", "a", "b")
        second = await routes.route(a, b, settings.now(), "WALK", "x", "y")
        assert (first.origin_id, second.origin_id) == ("a", "x")
    finally:
        await transport.close()


async def test_cancel_stops_work(repository, outing_settings, request_body):
    service = OutingService(repository, outing_settings)
    cancelled = asyncio.Event()

    async def block(*args):
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.set()

    service.llm.interpret = block
    stream = service.stream(request_body)
    await anext(stream)
    await stream.aclose()
    assert cancelled.is_set()
    assert not service.store.results
    await service.close()


def test_currency_points_and_conditions_separate():
    from types import SimpleNamespace

    base = {
        "stackable": True,
        "card_id": "card-a",
        "kind": "OFFER",
        "title": "Demo",
        "source": "demo",
        "expires_at": datetime.now(UTC),
    }
    matches = [
        AmexValueMatch(
            **base, source_id="a", amount=Decimal(30), currency="USD", eligible=True, stacking_group="dining"
        ),
        AmexValueMatch(
            **base, source_id="b", amount=Decimal(10), currency="USD", eligible=True, stacking_group="dining"
        ),
        AmexValueMatch(
            **base, source_id="c", amount=Decimal(20), currency="EUR", eligible=True, stacking_group="culture"
        ),
        AmexValueMatch(**base, source_id="d", amount=Decimal(500), currency="USD", eligible=False),
        AmexValueMatch(**{**base, "kind": "REWARD"}, source_id="p", points=100, eligible=True, stacking_group="points"),
    ]
    stop = SimpleNamespace(entity=SimpleNamespace(amex_matches=matches))
    assert aggregate([stop, stop]) == ({"USD": Decimal(30), "EUR": Decimal(20)}, 100)


def test_api_stream_and_capabilities(client):
    assert client.get("/api/outing/capabilities").json()["mode"] == "demo"
    response = client.post(
        "/api/outings/stream", json={"customer_id": "cust-dining", "text": "dining shopping", "date": "2026-10-02"}
    )
    assert response.status_code == 200
    events = [json.loads(block[6:]) for block in response.text.strip().split("\n\n")]
    assert events[-1]["result"]["alternatives"]
    assert client.get("/api/outings/" + events[-1]["run_id"]).status_code == 200
    assert (
        client.post(
            "/api/outings/stream",
            headers={"Origin": "https://untrusted.example"},
            json={"customer_id": "cust-dining", "text": "dining", "date": "2026-10-02"},
        ).status_code
        == 403
    )


def test_modes_and_timezone_validation():
    with pytest.raises(ValidationError):
        OutingSettings(realtime=True, demo=True)
    with pytest.raises(ValidationError):
        OutingRequest(customer_id="a", text="dining", date=date(2026, 10, 2), timezone="Unknown/Place")


async def test_ssrf_and_jsonld():
    with pytest.raises(ProviderError):
        await public_url("http://127.0.0.1/", ["127.0.0.1"])
    with pytest.raises(ProviderError):
        await public_url("https://127.0.0.1/", ["127.0.0.1"])
    parser = JSONLDParser()
    parser.feed('<script type="application/ld+json">{"@type":"Event","name":"Concert"}</script>')
    assert parser.records[0]["name"] == "Concert"


def test_missing_and_closed_hours():
    from types import SimpleNamespace

    now = datetime(2026, 9, 21, 17, tzinfo=UTC)
    assert is_open(SimpleNamespace(facts={}), now, now + timedelta(hours=1)) is None
    assert (
        is_open(SimpleNamespace(facts={"business_status": "CLOSED_PERMANENTLY"}), now, now + timedelta(hours=1))
        is False
    )


async def test_realtime_mocked_transports_end_to_end(repository, request_body):
    settings = OutingSettings(
        demo=False,
        realtime=True,
        openai_key="test",
        model="configured-model",
        places_key="test",
        routing_key="test",
        event_key="test",
        search_key="test",
    )
    service = OutingService(repository, settings)
    await service.http.close()
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "api.openai.com":
            payload = json.loads(request.content)
            if payload["text"]["format"]["name"] == "Interpretation":
                value = {"categories": ["DINING", "SHOPPING", "EVENT"], "preferences": [], "clarification": None}
            else:
                facts = json.loads(payload["input"][1]["content"])
                value = {
                    "items": [
                        {
                            "entity_id": f["entity_id"],
                            "evidence_ids": f["evidence_ids"],
                            "sentence": "Selected for your requested activity mix.",
                        }
                        for f in facts
                    ]
                }
            return httpx.Response(
                200, json={"output": [{"content": [{"type": "output_text", "text": json.dumps(value)}]}]}
            )
        if request.url.host == "places.googleapis.com":
            query = json.loads(request.content)["textQuery"]
            identity = "restaurant" if query.startswith("restaurants") else "shop"
            return httpx.Response(
                200,
                json={
                    "places": [
                        {
                            "id": identity,
                            "displayName": {"text": identity},
                            "formattedAddress": identity + " Rome",
                            "location": {"latitude": 41.90, "longitude": 12.48},
                            "regularOpeningHours": {"periods": [{"open": {"day": 0, "hour": 0}}]},
                            "googleMapsUri": "https://maps.google.com/?cid=" + identity,
                        }
                    ]
                },
            )
        if request.url.host == "app.ticketmaster.com":
            return httpx.Response(
                200,
                json={
                    "_embedded": {
                        "events": [
                            {
                                "id": "event",
                                "name": "Concert",
                                "dates": {
                                    "start": {"dateTime": "2026-10-02T18:00:00Z"},
                                    "end": {"dateTime": "2026-10-02T19:00:00Z"},
                                },
                                "_embedded": {
                                    "venues": [
                                        {
                                            "id": "venue",
                                            "location": {"latitude": "41.91", "longitude": "12.49"},
                                            "address": {"line1": "Venue Road Rome"},
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                },
            )
        if request.url.host == "api.search.brave.com":
            return httpx.Response(
                200,
                json={
                    "web": {"results": [{"title": "Unverified expensive claim", "url": "https://example.com/event"}]}
                },
            )
        if request.url.host == "routes.googleapis.com":
            return httpx.Response(200, json={"routes": [{"duration": "300s", "distanceMeters": 400}]})
        raise AssertionError(request.url.host)

    service.http.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = [e async for e in service.stream(request_body)][-1].result
        assert result.mode == "realtime" and result.status == "PARTIAL"
        assert result.alternatives
        assert all(not s.entity.synthetic for a in result.alternatives for s in a.stops)
        assert all(not s.entity.amex_matches for a in result.alternatives for s in a.stops)
        assert any(a.routes for a in result.alternatives)
        assert "Unverified expensive claim" not in result.model_dump_json()
        assert set(calls) == {
            "api.openai.com",
            "places.googleapis.com",
            "app.ticketmaster.com",
            "api.search.brave.com",
            "routes.googleapis.com",
        }
    finally:
        await service.close()


async def test_consent_change_during_stream(repository, outing_settings, request_body):
    service = OutingService(repository, outing_settings)
    original = service.llm.interpret

    async def withdraw(*args):
        customer = repository.customer(request_body.customer_id)
        customer.consent.allowed = False
        repository.save_customer(customer)
        return await original(*args)

    service.llm.interpret = withdraw
    try:
        result = [e async for e in service.stream(request_body)][-1].result
        assert result.status == "ERROR" and not result.alternatives and not result.search_plan
    finally:
        await service.close()


async def test_deadline_and_explanation_failure(repository, outing_settings, request_body):
    service = OutingService(repository, outing_settings.model_copy(update={"deadline": 1}))

    async def delayed(*args):
        await asyncio.sleep(2)

    service.llm.explain = delayed
    try:
        result = [e async for e in service.stream(request_body)][-1].result
        assert result.status == "PARTIAL" and result.alternatives
        assert any("deadline" in w for w in result.warnings)
    finally:
        await service.close()


async def test_synthetic_matches_conditions_and_exclusive_points(repository, outing_settings, request_body):
    service = OutingService(repository, outing_settings)
    try:
        initial = [e async for e in service.stream(request_body)][-1].result
        matches = [m for a in initial.alternatives for s in a.stops for m in s.entity.amex_matches]
        assert {m.kind for m in matches} >= {"OFFER", "BENEFIT", "REWARD"}
        request_body.confirmed_condition_ids = list(dict.fromkeys(c for m in matches for c in m.condition_ids))
        result = [e async for e in service.stream(request_body)][-1].result
        assert result.alternatives[0].totals_by_currency == {"USD": Decimal(40)}
        assert result.alternatives[0].reward_points == 0  # alternative to cash in same group
        assert any(m.included for s in result.alternatives[0].stops for m in s.entity.amex_matches)
    finally:
        await service.close()


async def test_low_confidence_prices_and_field_specific_authority(outing_settings, request_body):
    demo = Demo(outing_settings)
    candidate = (await demo.search(await demo.interpret(request_body, [])))[0]
    from agent.outing.verification import evidence

    item = evidence(
        "demo",
        "price",
        {"amount": 100, "currency": "EUR"},
        "demo:price",
        "DEMO",
        outing_settings.now(),
        outing_settings,
        True,
    )
    item.confidence = 0.3
    candidate.evidence.append(item)
    assert "price" not in VerificationService(outing_settings).verify(candidate).facts
    item.confidence = 0.95
    official = item.model_copy(
        update={
            "evidence_id": "official-price",
            "source_type": "OFFICIAL_ORGANIZER",
            "value": {"amount": 50, "currency": "EUR"},
        }
    )
    candidate.evidence.append(official)
    entity = VerificationService(outing_settings).verify(candidate)
    assert entity.facts["price"]["amount"] == 50 and "price" in entity.conflicts
    restricted = outing_settings.model_copy(update={"field_source_priority": {"price": {"DEMO": 100}}})
    assert VerificationService(restricted).verify(candidate).facts["price"]["amount"] == 100


async def test_event_dedup_preserves_recurring_occurrences(outing_settings, request_body):
    demo = Demo(outing_settings)
    event = (await demo.search(await demo.interpret(request_body, [])))[-1]
    for source in event.evidence:
        source.source_type = "TICKETING_API"
    duplicate = event.model_copy(deep=True, update={"candidate_id": "official-event", "provider": "official"})
    assert len(deduplicate([event, duplicate])) == 1
    for source in duplicate.evidence:
        if source.field == "schedule.start":
            source.value = "2026-10-03T20:00:00+02:00"
    assert len(deduplicate([event, duplicate])) == 2

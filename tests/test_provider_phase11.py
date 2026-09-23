from datetime import timedelta

import pytest

from agent.outing.config import OutingSettings
from agent.outing.demo import Demo
from agent.outing.models import OutingRequest
from agent.outing.verification import VerificationService


def test_provider_capabilities_are_safe(client):
    response = client.get("/api/v1/providers/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["providers"]["places"]["provider"] == "google_places"
    assert data["providers"]["web_discovery"]["role"] == "discovery_only"
    assert data["providers"]["amex_experiences"]["configured"] is False
    assert data["secrets_exposed"] is False
    assert "key" not in str(data).lower()


@pytest.mark.asyncio
async def test_demo_provider_is_explicitly_synthetic():
    settings = OutingSettings(demo=True, realtime=False)
    demo = Demo(settings)
    plan = await demo.interpret(OutingRequest(customer_id="cust-dining", text="dining", city="Rome", date="2026-10-02"), [])
    candidates = await demo.search(plan)
    assert candidates and all(e.synthetic for c in candidates for e in c.evidence)


def test_freshness_policy_suppresses_expired_facts():
    outing_settings = OutingSettings(demo=True, realtime=False)
    from agent.outing.models import DiscoveryCandidate
    from agent.outing.verification import evidence

    now = outing_settings.now()
    candidate = DiscoveryCandidate(
        candidate_id="place:x",
        name="X",
        category="DINING",
        provider="test",
        url="https://example.test",
        evidence=[
            evidence("test", "name", "X", "https://example.test", "PLACES_API", now, outing_settings),
            evidence("test", "address", "1 Rome", "https://example.test", "PLACES_API", now, outing_settings),
            evidence(
                "test",
                "location",
                {"lat": 41.9, "lng": 12.5},
                "https://example.test",
                "PLACES_API",
                now,
                outing_settings,
            ),
            evidence(
                "test",
                "opening_hours",
                [{"open": {"day": 0, "hour": 1}}],
                "https://example.test",
                "PLACES_API",
                now - timedelta(hours=7),
                outing_settings,
            ),
        ],
    )
    entity = VerificationService(outing_settings).verify(candidate)
    assert entity.freshness["opening_hours"] == "STALE"
    assert "opening_hours" not in entity.facts

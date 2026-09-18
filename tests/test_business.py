"""Business journeys exercise the real graph and SQLite through public endpoints."""

import httpx
import pytest
from fastapi.testclient import TestClient

from agent.business.extraction import LLMGoalExtractor
from agent.main import create_app
from config.settings import Settings


def journey(client, scenario="bakery"):
    selected = next(s for s in client.get("/api/business/scenarios").json() if s["scenario_id"] == scenario)
    detected = client.post(
        "/api/business/intents/detect", json={k: selected[k] for k in ("business_id", "goal_id", "signal_ids")}
    )
    assert detected.status_code == 200, detected.text
    intent = detected.json()["intent"]
    result = client.post(
        "/api/business/companion", json={"business_id": selected["business_id"], "intent_id": intent["intent_id"]}
    )
    assert result.status_code == 200, result.text
    return selected, intent, result.json()


def test_personalized_business_journeys(client):
    _, _, bakery = journey(client)
    _, _, consulting = journey(client, "consultancy")
    assert bakery["status"] == consulting["status"] == "ready"
    assert {r["recommendation_id"] for r in bakery["recommendations"]} != {
        r["recommendation_id"] for r in consulting["recommendations"]
    }
    assert bakery["totals_by_product"]["biz-flow"] == {"savings": "100.00", "rewards": "80.00"}
    assert consulting["totals_by_product"]["biz-flow"]["savings"] == "60.00"
    assert all(r["evidence"] for r in bakery["recommendations"])


def test_business_dismiss_replay_restore(client):
    scenario, intent, _ = journey(client)
    route = f"/api/business/intents/{intent['intent_id']}/feedback"
    body = {"owner_id": scenario["business_id"], "action": "dismiss"}
    assert client.post(route, json=body).status_code == 200
    _, _, result = journey(client)
    assert result["status"] == "abstained" and not result["recommendations"]
    assert client.post(route, json=body | {"action": "restore"}).status_code == 200
    assert journey(client)[2]["status"] == "ready"


@pytest.mark.parametrize(
    "code,status,offers",
    [("DEMO-PACKAGING", "verified", True), ("DEMO-NO-OFFER", "verified", False), ("DEMO-UNKNOWN", "unknown", False)],
)
def test_business_merchant_outcomes(client, code, status, offers):
    result = client.post(
        "/api/merchant/resolve", json={"owner_type": "business", "owner_id": "biz-bakery", "code": code}
    ).json()
    assert result["status"] == status
    assert bool(result["offers"]) == offers


def test_consent_and_ownership(client):
    _, intent, _ = journey(client)
    assert (
        client.post(
            "/api/business/companion", json={"business_id": "biz-consultancy", "intent_id": intent["intent_id"]}
        ).status_code
        == 404
    )
    client.put("/api/businesses/biz-bakery/consent", json={"allowed": False, "purpose": "personalization"})
    result = client.post(
        "/api/business/companion", json={"business_id": "biz-bakery", "intent_id": intent["intent_id"]}
    ).json()
    assert result["status"] == "abstained"


def test_extraction_is_only_draft(client):
    response = client.post(
        "/api/business/goals/extract",
        json={
            "business_id": "biz-bakery",
            "text": "Expand to a second location with packaging and an oven in the next 3 months",
        },
    )
    assert response.status_code == 200
    draft = response.json()
    assert draft["goal_type"] == "expansion"
    assert set(draft["categories"]) == {"packaging", "equipment"}
    assert "intent_id" not in draft


def test_duplicate_signals_do_not_inflate(client):
    selected, intent, experience = journey(client)
    signal = client.get(
        f"/api/business/intents/{intent['intent_id']}/signals", params={"business_id": selected["business_id"]}
    ).json()[0]
    assert client.post("/api/business/signals", json=signal).json()["status"] == "duplicate"
    _, next_intent, next_experience = journey(client)
    assert next_intent["confidence"] == intent["confidence"]
    assert next_experience["spend_summary"] == experience["spend_summary"]


def test_upgrade_preserves_controls_and_feedback(tmp_path):
    settings = Settings(database_path=str(tmp_path / "demo.sqlite3"))
    with TestClient(create_app(settings)) as first:
        selected, intent, _ = journey(first)
        first.put("/api/businesses/biz-bakery/preferences", json={"priorities": ["packaging"]})
        first.post(
            f"/api/business/intents/{intent['intent_id']}/feedback",
            json={"owner_id": selected["business_id"], "action": "dismiss"},
        )
    with TestClient(create_app(settings)) as second:
        assert second.get("/api/businesses/biz-bakery").json()["priorities"] == ["packaging"]
        assert journey(second)[2]["status"] == "abstained"


@pytest.mark.parametrize(
    "code,status,offers",
    [("DEMO-DINING", "verified", True), ("DEMO-NO-OFFER", "verified", False), ("DEMO-UNKNOWN", "unknown", False)],
)
def test_consumer_merchant_outcomes(client, code, status, offers):
    result = client.post(
        "/api/merchant/resolve", json={"owner_type": "consumer", "owner_id": "cust-dining", "code": code}
    ).json()
    assert result["status"] == status
    assert bool(result["offers"]) == offers


@pytest.mark.asyncio
async def test_invalid_llm_extraction_falls_back():
    settings = Settings(llm_endpoint="https://example.test/chat", llm_model="mock", llm_api_key="synthetic")
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, json={"choices": [{"message": {"content": '{"goal_type":"expansion","amount":999}'}}]}
        )
    )
    result = await LLMGoalExtractor(settings, transport).extract("Expand with packaging")
    assert result.provider_mode == "deterministic"
    assert result.goal_type == "expansion"

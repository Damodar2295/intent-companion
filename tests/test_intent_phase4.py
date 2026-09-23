from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent.domain import IntentSignal
from agent.intent_extraction import IntentExtractor
from agent.intent_service import IntentService
from agent.llm.adapters import MockLLMAdapter
from agent.llm.contracts import ModelRoute
from agent.llm.gateway import LLMGateway
from agent.llm.router import ModelRouter
from agent.main import create_app
from agent.repositories import Abstain, Conflict
from config.settings import Settings

TEXT = "Destination: Paris; activity: dining; 2026-10-10 to 2026-10-15."


@pytest.fixture
def signal(repository):
    payload = repository.signals("cust-dining")[0].model_dump(mode="json")
    payload.update(event_id="phase4-signal", event_type="event_booking")
    payload["context"].update(destination="Paris", intent_type=None)
    return payload


@pytest.mark.parametrize(
    "kind,declared,expected,stage",
    [
        ("travel_booking", None, "travel", "booked"),
        ("restaurant_booking", None, "dining", "booked"),
        ("event_booking", None, "event", "booked"),
        ("event_search", None, "event", "exploring"),
        ("customer_declared_intent", "shopping", "shopping", "planning"),
        ("customer_declared_intent", "lifestyle", "lifestyle", "planning"),
    ],
)
def test_classification_and_stage(repository, settings, signal, kind, declared, expected, stage):
    signal["event_type"] = kind
    signal["context"]["intent_type"] = declared
    engine = IntentService(repository, settings)
    intent = engine.derive(repository.customer("cust-dining"), [IntentSignal.model_validate(signal)])
    assert intent.intent_type == expected and intent.intent_stage == stage
    assert intent.destination == "Paris"
    assert all("Paris" in e.fact and "Rome" not in e.fact for e in intent.evidence)
    debug = engine.diagnostics(intent)
    assert debug["confidence_is_probability"] is False
    assert intent.confidence == min(debug["uncapped_weight_sum"], 1)


def test_repeat_types_and_capped_confidence(repository, settings, signal):
    engine = IntentService(repository, settings)
    first = IntentSignal.model_validate(signal)
    repeated = first.model_copy(update={"event_id": "repeat"})
    declared = first.model_copy(update={"event_id": "declared", "event_type": "customer_declared_intent"}, deep=True)
    declared.context.intent_type = "event"
    intent = engine.derive(repository.customer("cust-dining"), [first, repeated, declared, first])
    assert intent.confidence == 1
    assert sorted(e.weight for e in intent.evidence) == [0, 0.9, 0.9]
    assert len(intent.signal_ids) == 3
    with pytest.raises(Conflict):
        engine.derive(repository.customer("cust-dining"), [first, first.model_copy(update={"source": "different"})])


def test_trip_booking_not_inferred_from_restaurant(repository, settings, signal):
    engine = IntentService(repository, settings)
    first = IntentSignal.model_validate(signal).model_copy(update={"event_type": "travel_search"})
    dining = first.model_copy(update={"event_id": "dinner", "event_type": "restaurant_booking"})
    intent = engine.derive(repository.customer("cust-dining"), [first, dining])
    assert intent.intent_type == "travel" and intent.intent_stage == "planning"


def test_ambiguous_and_conflicting_contexts(repository, settings, signal):
    engine = IntentService(repository, settings)
    first = IntentSignal.model_validate(signal)
    other = first.model_copy(update={"event_id": "other"}, deep=True)
    other.context.destination = "Milan"
    with pytest.raises(Abstain, match="destinations"):
        engine.derive(repository.customer("cust-dining"), [first, other])
    first.context.intent_type = "shopping"
    with pytest.raises(Abstain, match="conflicts"):
        engine.ingest(first)
    first.context.intent_type = None
    first.event_type = "ad_click"
    with pytest.raises(Abstain, match="unclear"):
        engine.derive(repository.customer("cust-dining"), [first])


def test_ttl_and_threshold_configuration(repository, settings, signal):
    engine = IntentService(repository, settings)
    settings.signal_ttl_overrides = {"event_search": 2}
    settings.intent_planning_threshold = 0.1
    first = IntentSignal.model_validate(signal).model_copy(
        update={"event_type": "event_search", "timestamp": settings.now() - timedelta(days=1)}
    )
    intent = engine.derive(repository.customer("cust-dining"), [first])
    assert intent.intent_stage == "planning"
    assert intent.expires_at == settings.now() + timedelta(days=1)
    first.timestamp -= timedelta(days=1)
    with pytest.raises(Abstain, match="expired"):
        engine.derive(repository.customer("cust-dining"), [first])


def test_general_api_ingest_detect_and_legacy_boundary(client, signal):
    signal["event_type"] = " Event-Reservation "
    assert client.post("/api/v1/intent/signals", json=signal).json()["status"] == "created"
    assert client.post("/api/v1/intent/signals", json=signal).json()["status"] == "duplicate"
    body = {"customer_id": "cust-dining", "signal_ids": [signal["event_id"]], "debug": True}
    response = client.post("/api/v1/intent/detect", json=body)
    result = response.json()
    assert response.status_code == 200 and result["intent"]["intent_type"] == "event"
    assert result["intent"]["intent_stage"] == "booked" and result["debug"]["uncapped_weight_sum"] == 0.9
    wrong = client.post("/api/v1/intent/detect", json=body | {"customer_id": "cust-stay"})
    assert wrong.status_code == 404
    companion = client.post(
        "/api/companion", json={"customer_id": "cust-dining", "intent_id": result["intent"]["intent_id"]}
    )
    assert companion.json()["status"] == "abstained"
    body["debug"] = False
    assert "debug" not in client.post("/api/v1/intent/detect", json=body).json()


def test_consent_and_suppressed_preferences(client, signal):
    client.post("/api/customers/cust-dining/preferences/remove", json={"preference": "fine dining"}).raise_for_status()
    signal["context"]["preferences"] = ["fine dining"]
    client.post("/api/v1/intent/signals", json=signal).raise_for_status()
    body = {"customer_id": "cust-dining", "signal_ids": [signal["event_id"]]}
    result = client.post("/api/v1/intent/detect", json=body).json()
    assert "fine dining" not in result["intent"]["preferences"]
    client.put("/api/customers/cust-dining/consent", json={"allowed": False}).raise_for_status()
    assert client.post("/api/v1/intent/detect", json=body).json()["status"] == "abstained"
    assert client.post("/api/v1/intent/signals", json=signal).status_code == 422
    assert (
        client.post(
            "/api/v1/intent/extract", json={"customer_id": "cust-dining", "text": TEXT, "consent": {"allowed": True}}
        ).status_code
        == 422
    )


async def test_deterministic_extraction_no_persistence(client):
    before = len(client.app.state.repository.signals("cust-dining"))
    body = {"customer_id": "cust-dining", "text": TEXT, "consent": {"allowed": True}}
    response = client.post("/api/v1/intent/extract", json=body)
    data = response.json()
    assert data["status"] == "ready_for_review" and data["context"]["intent_type"] == "dining"
    assert data["context"]["destination"] == "Paris" and data["requires_confirmation"]
    assert all(e["quote"] in TEXT for e in data["evidence"])
    assert len(client.app.state.repository.signals("cust-dining")) == before
    assert client.post("/api/v1/intent/extract", json=body | {"consent": {"allowed": False}}).status_code == 422


@pytest.mark.parametrize(
    "text", ["dining in Rome tonight", "Travel to Paris or Rome in October", "dining in Rome 2026-10-15 to 2026-10-10"]
)
async def test_ambiguous_draft_requests_clarification(text):
    result = await IntentExtractor().extract(text)
    assert result.status == "needs_clarification" and result.requires_confirmation


async def test_ungrounded_llm_output_and_failure_fallback():
    gateway = LLMGateway(
        ModelRouter({"intent.entity_extraction": ModelRoute("mock", "fixture", "lightweight")}),
        {
            "mock": MockLLMAdapter(
                {
                    "intent.entity_extraction": {
                        "destination": "London",
                        "start_date": "2026-10-10",
                        "end_date": "2026-10-15",
                        "activity": "dining",
                    }
                }
            )
        },
    )
    result = await IntentExtractor(gateway, "llm").extract(TEXT)
    assert result.fallback_reason and result.context.destination == "Paris"
    gateway.adapters["mock"] = MockLLMAdapter({})
    result = await IntentExtractor(gateway, "llm").extract(TEXT)
    assert result.fallback_reason and result.provider_mode == "deterministic"


def test_mock_mode_uses_gateway_without_network():
    with TestClient(create_app(Settings(database_path=":memory:", intent_extraction_mode="mock"))) as client:
        result = client.post(
            "/api/v1/intent/extract", json={"customer_id": "cust-dining", "text": TEXT, "consent": {"allowed": True}}
        ).json()
        assert result["provider_mode"] == "mock" and result["status"] == "ready_for_review"


def test_invalid_configuration():
    with pytest.raises(ValidationError):
        Settings(signal_ttl_overrides={"unknown": 1})
    with pytest.raises(ValidationError):
        Settings(intent_planning_threshold=1.5)
    with pytest.raises(ValidationError):
        Settings(weights={"ad_click": 0.1})


def test_consent_withdrawal_during_extraction(client):
    original = client.app.state.intent_extractor

    class WithdrawWhileAwaiting:
        async def extract(self, text):
            draft = await original.extract(text)
            customer = client.app.state.repository.customer("cust-dining")
            customer.consent.allowed = False
            client.app.state.repository.save_customer(customer)
            return draft

    client.app.state.intent_extractor = WithdrawWhileAwaiting()
    result = client.post(
        "/api/v1/intent/extract", json={"customer_id": "cust-dining", "text": TEXT, "consent": {"allowed": True}}
    )
    assert result.status_code == 422 and "withdrawn during" in result.json()["detail"]


def test_mock_uses_shared_gateway():
    with TestClient(create_app(Settings(database_path=":memory:", intent_extraction_mode="mock"))) as client:
        assert client.app.state.intent_extractor.gateway is client.app.state.llm_gateway

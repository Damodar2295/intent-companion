import asyncio
from datetime import UTC, datetime

import pytest

from agent.llm.contracts import LLMError
from agent.search.parsing import interpret_mock
from agent.search.service import OPERATION, planner_mode
from config.settings import Settings


def body(**changes):
    return {
        "customer_id": "cust-dining",
        "consent": {"allowed": True},
        "text": "Plan dining and shopping in Rome tomorrow at 6pm for three hours under EUR 100 with Amex offers",
        "timezone": "Europe/Rome",
        **changes,
    }


def post(client, **changes):
    return client.post("/api/v1/search/plan", json=body(**changes))


def handler(client, fn):
    client.app.state.llm_gateway.adapters["mock"].handlers[OPERATION] = fn


def test_ready_requirements(client):
    response = post(client)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "READY"
    assert result["provider_mode"] == "mock"
    plan = result["search_plan"]
    assert plan["outing"]["date"] == "2026-09-18"
    assert plan["outing"]["start_time"] == "18:00:00"
    assert plan["outing"]["end_time"] == "21:00:00"
    assert plan["outing"]["budget"] == "100"
    assert plan["requires_amex_value"] and plan["requires_routing"]
    assert plan["origin_reference"] == "UNSPECIFIED"
    assert plan["evidence"] and "places" not in plan


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"city": "Paris"}, "city"),
        ({"date": "2026-09-19"}, "date"),
        ({"budget": "200"}, "budget"),
        ({"currency": "USD"}, "currency"),
        ({"end_time": "22:00"}, "end_time"),
        (
            {"travel_mode": "DRIVE", "text": "Plan dinner in Rome tomorrow at 6pm for three hours walking"},
            "travel_mode",
        ),
        ({"timezone": None}, "timezone"),
        ({"timezone": "invalid"}, "timezone"),
        ({"text": "Plan dinner near my hotel in Rome tomorrow at 6pm for three hours"}, "user_location"),
        ({"text": "Plan dinner in Rome tomorrow"}, "start_time"),
        ({"text": "Plan dinner in Rome tomorrow at 6pm for three hours under 100"}, "currency"),
        ({"text": "Plan dinner in Rome tomorrow at 11pm for three hours"}, "end_time"),
        ({"include_amex_value": False}, "include_amex_value"),
        ({"text": "Plan dinner in Rome tomorrow at 6pm for three hours without shopping"}, "text"),
    ],
)
def test_clarifications(client, changes, field):
    result = post(client, **changes).json()
    assert result["status"] == "CLARIFICATION_REQUIRED", result
    assert field in result["clarification_fields"]
    assert result["search_plan"] is None


def test_benefits_only(client):
    result = post(client, text="Dining Amex benefits", timezone=None).json()
    assert result["status"] == "READY"
    plan = result["search_plan"]
    assert plan["task"] == "BENEFIT_LOOKUP"
    assert plan["outing"] is None
    assert not plan["requires_routing"] and not plan["requires_real_world_discovery"]


def test_destination_local_day(client):
    client.app.state.settings.demo_now = datetime(2026, 9, 17, 23, 30, tzinfo=UTC)
    result = post(client).json()
    assert result["search_plan"]["outing"]["date"] == "2026-09-19"


def test_dst_ambiguity(client):
    result = post(client, text="Plan dinner in Rome", date="2026-10-25", start_time="02:15", end_time="04:00").json()
    assert result["status"] == "CLARIFICATION_REQUIRED"


def test_consent_required(client):
    assert post(client, consent={"allowed": False}).status_code == 403


def test_invalid_body(client):
    assert post(client, budget=-10).status_code == 422


def test_model_cannot_invent_or_omit_facts(client):
    draft = interpret_mock(body()["text"]).model_dump()
    draft["budget_quote"] = "under EUR 1"
    handler(client, draft)
    assert post(client).json()["status"] == "CLARIFICATION_REQUIRED"
    draft["budget_quote"] = None
    assert post(client).json()["status"] == "CLARIFICATION_REQUIRED"


def test_invalid_model_schema(client):
    handler(client, {"savings": 1000})
    assert post(client).status_code == 503


def test_timeout_and_cancellation(client):
    async def slow(_):
        await asyncio.sleep(1)

    handler(client, slow)
    client.app.state.settings.search_plan_timeout = 0.001
    assert post(client).status_code == 503


def test_provider_error_no_fallback(client):
    def unavailable(_):
        raise LLMError("unavailable")

    handler(client, unavailable)
    assert post(client).status_code == 503


def test_no_personal_context_sent_to_gateway(client):
    def capture(request):
        assert "cust-dining" not in str(request.messages)
        assert "41.9" not in str(request.messages)
        return interpret_mock(body()["text"]).model_dump()

    handler(client, capture)
    assert post(client, user_location={"lat": 41.9, "lng": 12.5}).status_code == 200


def test_realtime_mock_rejected():
    with pytest.raises(ValueError, match="Realtime"):
        planner_mode(Settings(demo_mode=False, search_plan_mode="mock"))
    assert planner_mode(Settings(demo_mode=False)) == "llm"


@pytest.mark.parametrize("withdraw", [True, False])
def test_context_change_during_model_call(client, withdraw):
    def change(_):
        repo = client.app.state.repository
        customer = repo.customer("cust-dining")
        if withdraw:
            customer.consent.allowed = False
        else:
            customer.stated_preferences = []
        repo.save_customer(customer)
        return interpret_mock(body()["text"]).model_dump()

    handler(client, change)
    assert post(client).status_code == (403 if withdraw else 409)


def test_suppressed_preferences_not_used(client):
    repo = client.app.state.repository
    customer = repo.customer("cust-dining")
    customer.suppressed_preferences = customer.stated_preferences.copy()
    repo.save_customer(customer)
    result = post(client).json()
    assert result["search_plan"]["preferences"] == []
    assert result["search_plan"]["outing"]["preferences"] == []


async def test_cancellation_propagates(client):
    from agent.search.models import SearchPlanRequest

    started = asyncio.Event()

    async def wait(_):
        started.set()
        await asyncio.Event().wait()

    handler(client, wait)
    task = asyncio.create_task(client.app.state.search_planner.plan(SearchPlanRequest(**body())))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_optional_intent_context(client):
    intent = client.app.state.intents.detect("cust-dining")
    result = post(
        client,
        intent_id=intent.intent_id,
        text="Plan dinner",
        date=str(intent.start_date),
        start_time="18:00",
        end_time="21:00",
    ).json()
    assert result["status"] == "READY", result
    assert result["search_plan"]["outing"]["city"] == intent.destination
    assert post(client, customer_id="cust-prospect", intent_id=intent.intent_id).status_code == 404


async def test_configured_responses_integration(repository, settings):
    import json

    import httpx

    from agent.intent_service import IntentService
    from agent.outing.config import OutingSettings
    from agent.outing.providers import Transport
    from agent.providers.container import build_gateway
    from agent.search.models import SearchPlanRequest
    from agent.search.service import SearchPlanner

    settings.search_plan_mode = "llm"
    outing = OutingSettings(model="configured-test-model", openai_key="test-key")
    calls = []

    def respond(request):
        wire = json.loads(request.content)
        calls.append(wire)
        assert wire["model"] == "configured-test-model"
        assert wire["text"]["format"]["strict"] is True
        return httpx.Response(
            200,
            json={
                "output": [
                    {"content": [{"type": "output_text", "text": interpret_mock(body()["text"]).model_dump_json()}]}
                ]
            },
        )

    http = Transport(outing, httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    try:
        gateway = build_gateway(settings, outing, http)
        planner = SearchPlanner(repository, settings, gateway, IntentService(repository, settings), "llm")
        result = await planner.plan(SearchPlanRequest(**body()))
        assert result.status == "READY" and result.provider_mode == "llm"
        assert len(calls) == 1
    finally:
        await http.close()


async def test_missing_llm_configuration_is_actionable(repository, settings):
    from fastapi import HTTPException

    from agent.providers.container import build_gateway
    from agent.search.models import SearchPlanRequest
    from agent.search.service import SearchPlanner

    settings.search_plan_mode = "llm"
    planner = SearchPlanner(repository, settings, build_gateway(settings), None, "llm")
    with pytest.raises(HTTPException) as error:
        await planner.plan(SearchPlanRequest(**body()))
    assert error.value.status_code == 503
    assert "credentials" in error.value.detail

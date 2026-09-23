import asyncio

import pytest

from agent.search.models import SearchPlanRequest
from agent.tools.service import ToolBinding, select_tools


def request(**changes):
    return {
        "customer_id": "cust-dining",
        "consent": {"allowed": True},
        "text": "Plan dinner in Rome tomorrow at 6pm for three hours",
        "timezone": "Europe/Rome",
        **changes,
    }


def execute(client, **changes):
    return client.post("/api/v1/search/execute", json=request(**changes))


def test_demo_discovery(client):
    response = execute(client)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "READY"
    assert [t["tool"] for t in data["trace"]] == ["search_plan", "places"]
    assert data["outputs"][0]["candidates"][0]["provider"] == "demo"
    assert data["outputs"][0]["usage"] == "DISCOVERY_ONLY"
    assert "routing" in data["deferred"]


def test_benefits_only_never_discovers(client):
    response = execute(client, text="Dining Amex benefits", city="Rome")
    data = response.json()
    assert data["status"] == "READY"
    assert {t["tool"] for t in data["trace"]} == {"search_plan", "cards", "benefits", "offers", "rewards"}
    assert not data["deferred"]
    assert all(o["usage"] == "ILLUSTRATIVE_CATALOG_NOT_ELIGIBILITY" for o in data["outputs"])


def test_missing_provider_explicit_partial(client):
    data = execute(client, text="Plan concert and dinner in Rome tomorrow at 6pm for three hours").json()
    assert data["status"] == "PARTIAL"
    assert {t["tool"]: t["status"] for t in data["trace"]}["web"] == "UNAVAILABLE"
    assert {o["tool"] for o in data["outputs"]} == {"places", "events"}


def test_clarification_no_tools(client):
    data = execute(client, timezone=None).json()
    assert data["status"] == "CLARIFICATION_REQUIRED"
    assert len(data["trace"]) == 1 and not data["outputs"]


def test_consent_denial(client):
    assert execute(client, consent={"allowed": False}).status_code == 403


def test_limits_and_safe_provider_error(client, caplog):
    orchestrator = client.app.state.tool_orchestrator

    async def fail(_):
        raise RuntimeError("secret-token-and-private-text")

    orchestrator.bindings["places"] = ToolBinding(fail, True)
    data = execute(client).json()
    assert data["status"] == "ERROR"
    assert data["trace"][-1]["status"] == "FAILED"
    assert "secret-token" not in str(data) + caplog.text


async def test_parallel_and_concurrency_limit(client):
    orchestrator = client.app.state.tool_orchestrator
    orchestrator.semaphore = asyncio.Semaphore(2)
    active = peak = count = 0
    gate = asyncio.Event()

    async def tool(_):
        nonlocal active, peak, count
        active += 1
        count += 1
        peak = max(peak, active)
        if active == 2:
            gate.set()
        await asyncio.wait_for(gate.wait(), 0.5)
        await asyncio.sleep(0.01)
        active -= 1
        return []

    for name in ("cards", "benefits", "offers", "rewards"):
        orchestrator.bindings[name] = ToolBinding(tool, False)
    result = await orchestrator.execute(SearchPlanRequest(**request(text="Dining Amex benefits")))
    assert result.status == "EMPTY"
    assert peak == 2 and count == 4


@pytest.mark.parametrize("run_timeout", [False, True])
async def test_timeout_retains_completed_work(client, run_timeout):
    orchestrator = client.app.state.tool_orchestrator
    cancelled = asyncio.Event()

    async def slow(_):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    orchestrator.bindings["places"] = ToolBinding(slow, True)
    if run_timeout:
        orchestrator.settings.tool_run_deadline = 0.05
    else:
        orchestrator.settings.tool_timeout = 0.02
    result = await orchestrator.execute(
        SearchPlanRequest(**request(text="Plan dinner in Rome tomorrow at 6pm for three hours with Amex offers"))
    )
    assert result.status == "PARTIAL"
    assert cancelled.is_set()
    assert next(t for t in result.trace if t.tool == "places").status == "TIMED_OUT"
    assert any(o.catalog for o in result.outputs)


async def test_cancellation_stops_children(client):
    orchestrator = client.app.state.tool_orchestrator
    started, ended = asyncio.Event(), asyncio.Event()

    async def slow(_):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            ended.set()

    orchestrator.bindings["places"] = ToolBinding(slow, True)
    task = asyncio.create_task(orchestrator.execute(SearchPlanRequest(**request())))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ended.is_set()


@pytest.mark.parametrize("withdraw", [True, False])
def test_context_change_discards_outputs(client, withdraw):
    orchestrator = client.app.state.tool_orchestrator

    async def change(_):
        customer = orchestrator.repository.customer("cust-dining")
        if withdraw:
            customer.consent.allowed = False
        else:
            customer.stated_preferences = []
        orchestrator.repository.save_customer(customer)
        return []

    orchestrator.bindings["places"] = ToolBinding(change, True)
    response = execute(client)
    assert response.status_code == (403 if withdraw else 409)
    assert "outputs" not in response.json()


def test_invocation_budget(client):
    client.app.state.settings.tool_max_calls = 1
    data = execute(client, text="Dining Amex benefits").json()
    assert data["status"] == "PARTIAL"
    assert [t["status"] for t in data["trace"][2:]] == ["SKIPPED"] * 3


def test_result_limit(client):
    client.app.state.settings.tool_result_limit = 1
    data = execute(client, text="Dining Amex benefits", city="Rome").json()
    assert all(len(o["catalog"]) <= 1 for o in data["outputs"])
    assert any(t["truncated"] for t in data["trace"])


def test_invalid_tool_output(client):
    async def invalid(_):
        return [{"invented_savings": 1000}]

    client.app.state.tool_orchestrator.bindings["places"] = ToolBinding(invalid, True)
    data = execute(client).json()
    assert data["status"] == "ERROR"
    assert not data["outputs"]


def test_amex_experience_not_invented(client):
    data = execute(client, text="Plan Amex experiences in Rome tomorrow at 6pm for three hours").json()
    assert next(t for t in data["trace"] if t["tool"] == "amex_experiences")["status"] == "UNAVAILABLE"


def test_no_realtime_synthetic_discovery(repository):
    from agent.outing.config import OutingSettings
    from agent.tools.composition import build_tools

    bindings = build_tools(repository, OutingSettings(demo=False, realtime=True), None)
    assert not {"places", "events", "web"} & bindings.keys()


def test_tool_selection_deterministic(client):
    plan = client.post("/api/v1/search/plan", json=request()).json()["search_plan"]
    from agent.search.models import SearchRequirements

    assert select_tools(SearchRequirements(**plan)) == ["places"]


def test_global_catalog_empty_does_not_invent_destination(client):
    data = execute(client, text="Dining Amex benefits").json()
    assert data["status"] == "EMPTY"
    assert data["planning"]["search_plan"]["destination"] is None


async def test_run_deadline_includes_planning(client):
    orchestrator = client.app.state.tool_orchestrator
    orchestrator.settings.tool_run_deadline = 0.01

    async def slow(_):
        await asyncio.Event().wait()

    orchestrator.planner.plan = slow
    result = await orchestrator.execute(SearchPlanRequest(**request()))
    assert result.status == "ERROR"
    assert result.trace[0].status == "TIMED_OUT"
    assert not result.outputs


async def test_queued_tools_cancelled_at_run_deadline(client):
    orchestrator = client.app.state.tool_orchestrator
    orchestrator.settings.tool_run_deadline = 0.02
    orchestrator.semaphore = asyncio.Semaphore(1)
    calls = []

    async def slow(_):
        calls.append(1)
        await asyncio.Event().wait()

    for name in ("cards", "benefits", "offers", "rewards"):
        orchestrator.bindings[name] = ToolBinding(slow, False)
    result = await orchestrator.execute(SearchPlanRequest(**request(text="Dining Amex benefits")))
    assert len(calls) == 1
    assert all(t.status == "TIMED_OUT" for t in result.trace[1:])
    assert result.trace[2].started_at is None


def test_tool_traces_exclude_personal_inputs(client, caplog):
    caplog.set_level("INFO", logger="tools")
    execute(client, user_location={"lat": 41.9876543, "lng": 12.5123456})
    assert '"event": "tool_invocation"' in caplog.text
    assert "41.9876543" not in caplog.text
    assert "cust-dining" not in caplog.text
    assert request()["text"] not in caplog.text


async def test_http_disconnect_cancels_work():
    from fastapi import HTTPException

    from agent.tools.http import execute_connected

    started, stopped = asyncio.Event(), asyncio.Event()

    class Work:
        async def execute(self, body):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    class Disconnected:
        async def is_disconnected(self):
            await started.wait()
            return True

    with pytest.raises(HTTPException) as error:
        await execute_connected(Work(), None, Disconnected())
    assert error.value.status_code == 499
    assert stopped.is_set()

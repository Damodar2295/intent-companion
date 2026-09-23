import time
from collections import defaultdict, deque
from contextlib import aclosing
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent.outing.edit import OutingEditRequest
from agent.outing.grounding import build_response
from agent.outing.models import OutingRequest


def outing_routes(app):
    router = APIRouter()
    recent = defaultdict(deque)
    active = set()

    @router.get("/outing/capabilities")
    async def capabilities():
        return app.state.outing.settings.capabilities()

    @router.post("/outings/stream")
    async def stream(body: OutingRequest, request: Request):
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlparse

            if urlparse(origin).hostname not in {"localhost", "127.0.0.1", "::1", "testserver"}:
                raise HTTPException(403, "Outing requests are restricted to the local application")
        try:
            customer = app.state.repository.customer(body.customer_id)
        except KeyError:
            raise HTTPException(404, "Customer not found") from None
        if not customer.consent.allowed:
            raise HTTPException(403, "Enable personalization consent before planning an outing")
        if customer.segment != "consumer":
            raise HTTPException(422, "Outings are available for prospects and card members")
        if not app.state.outing.settings.capabilities()["llm"]:
            raise HTTPException(503, "Configure OPENAI_API_KEY and OPENAI_MODEL for realtime interpretation")
        now = time.monotonic()
        key = body.customer_id
        for old in list(recent):
            if not recent[old] or recent[old][-1] < now - 60:
                del recent[old]
        history = recent[key]
        while history and history[0] < now - 60:
            history.popleft()
        if key in active or len(history) >= 5:
            raise HTTPException(429, "An outing is already running or the local rate limit was reached")
        history.append(now)
        active.add(key)

        async def events():
            try:
                async with aclosing(app.state.outing.stream(body)) as stream:
                    async for event in stream:
                        if await request.is_disconnected():
                            break
                        yield "data: " + event.model_dump_json() + "\n\n"
            finally:
                active.discard(key)

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
        )

    @router.post("/v1/outings/plan")
    async def plan_json(body: OutingRequest):
        customer = app.state.repository.customer(body.customer_id)
        if not customer.consent.allowed:
            raise HTTPException(403, "Enable personalization consent before planning an outing")
        if customer.segment != "consumer":
            raise HTTPException(422, "Outings are available for prospects and card members")
        final = None
        async for event in app.state.outing.stream(body):
            if event.result is not None:
                final = event.result
        if final is None:
            raise HTTPException(500, "Outing planning did not produce a result")
        return final

    @router.get("/outings/{run_id}")
    async def retrieve(run_id: str):
        result = app.state.outing.store.get(run_id)
        if result is None:
            raise HTTPException(404, "Outing expired, consent changed, or run is unavailable")
        return result

    @router.get("/v1/outings/{run_id}/response")
    async def grounded_response(run_id: str):
        result = app.state.outing.store.get(run_id)
        if result is None:
            raise HTTPException(404, "Outing expired, consent changed, or run is unavailable")
        return build_response(result)

    @router.get("/v1/outings/{run_id}/diagnostics")
    async def diagnostics(run_id: str):
        result = app.state.outing.store.diagnostics(run_id)
        if result is None:
            raise HTTPException(404, "Outing expired, consent changed, or run is unavailable")
        return result

    @router.post("/v1/outings/{run_id}/edit")
    async def edit(run_id: str, body: OutingEditRequest):
        if body.operation == "CHANGE_CATEGORY" and not body.category:
            raise HTTPException(422, "category is required for CHANGE_CATEGORY")
        if body.operation == "REMOVE_STOP" and not body.stop_id:
            raise HTTPException(422, "stop_id is required for REMOVE_STOP")
        customer = app.state.repository.customer(body.customer_id)
        if not customer.consent.allowed:
            raise HTTPException(403, "Enable personalization consent before editing an outing")
        stored = app.state.outing.store.results.get(run_id)
        if stored is None or stored[0] != body.customer_id:
            raise HTTPException(404, "Outing expired, consent changed, or run is unavailable")
        result = app.state.outing.store.get(run_id)
        if result is None:
            raise HTTPException(404, "Outing expired, consent changed, or run is unavailable")
        if body.operation in {"ADD_STOP", "REPLACE_STOP"}:
            raise HTTPException(422, "New stops require a fresh verified outing plan; no place was invented.")
        if result.search_plan is None:
            raise HTTPException(409, "This outing has no editable search plan")
        edited = result.model_copy(deep=True)
        if body.operation == "CHANGE_BUDGET":
            if body.budget is None:
                raise HTTPException(422, "budget is required for CHANGE_BUDGET")
            edited.search_plan.budget = body.budget
            if body.currency:
                edited.search_plan.currency = body.currency
        elif body.operation == "CHANGE_CATEGORY":
            if body.category not in {"EVENT", "CULTURE", "DINING", "SHOPPING", "ATTRACTION", "EXPERIENCE"}:
                raise HTTPException(422, "Unsupported outing category")
            edited.search_plan.categories = [body.category]
            for alternative in edited.alternatives:
                alternative.stops = [s for s in alternative.stops if s.entity.entity_type == body.category]
                alternative.feasibility = "INCOMPLETE"
        elif body.operation == "REMOVE_STOP":
            found = False
            for alternative in edited.alternatives:
                before = len(alternative.stops)
                alternative.stops = [s for s in alternative.stops if s.entity.entity_id != body.stop_id]
                found |= before != len(alternative.stops)
                if before != len(alternative.stops):
                    alternative.feasibility = "INCOMPLETE"
            if not found:
                raise HTTPException(404, "Stop is not present in this outing")
        elif body.operation == "CHANGE_DURATION":
            if body.visit_minutes is None:
                raise HTTPException(422, "visit_minutes is required for CHANGE_DURATION")
            for alternative in edited.alternatives:
                for stop in alternative.stops:
                    if stop.entity.entity_type != "EVENT":
                        stop.departure = stop.arrival + timedelta(minutes=body.visit_minutes)
                        stop.duration_assumed = True
                        alternative.feasibility = "INCOMPLETE"
        edited.status = "PARTIAL"
        edited.warnings = list(
            dict.fromkeys(
                [*edited.warnings, "Edited plan requires fresh route/opening-hour validation before execution."]
            )
        )
        return edited

    return router

"""Thin API routes. Same-origin localhost demo; no permissive CORS or live integrations."""

import json
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from agent.domain import CompanionExperience, Consent, CustomerContext, IntentContext, IntentSignal, Model, Preference
from agent.extension_api import routes
from agent.initialize import lifespan
from agent.repositories import Abstain, Conflict, NotFound
from config.settings import ROOT, Settings

logger = logging.getLogger("intent_companion")


class DetectRequest(Model):
    customer_id: str
    signal_ids: list[str] | None = None


class DetectionResponse(Model):
    status: str
    intent: IntentContext | None = None
    abstention_reasons: list[str] = Field(default_factory=list)


class CompanionRequest(Model):
    customer_id: str
    intent_id: str


class RemovePreference(Model):
    preference: Preference


class PreferencesRequest(Model):
    preferences: list[Preference] = Field(max_length=6)


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="Intent Companion",
        version="1.0.0",
        lifespan=lifespan,
        description="Synthetic Rome travel demo. No real card, offer, merchant or approval claims.",
    )
    app.state.injected_settings = settings
    app.state.ready = False
    router = APIRouter()

    @app.exception_handler(NotFound)
    async def not_found(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = f"req-{uuid4().hex[:16]}"
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - final redaction boundary for unexpected server failures
            # Never expose exception text, DB paths or provider payloads.
            logger.error(json.dumps({"event": "request_failed", "request_id": request_id}))
            response = JSONResponse(status_code=500, content={"detail": "Unable to complete this request safely."})
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(elapsed)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "request_id": request_id,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": elapsed,
                }
            )
        )
        return response

    @router.get("/health")
    async def health():
        if not app.state.ready:
            raise HTTPException(503, "Not ready")
        return {
            "status": "ready",
            "synthetic": True,
            "demo_mode": app.state.settings.demo_mode,
            "clock": app.state.settings.now().isoformat(),
            "configured_provider": app.state.settings.ai_provider,
        }

    @router.get("/scenarios")
    async def scenarios():
        return json.loads((app.state.settings.fixture_dir / "scenarios.json").read_text())

    @router.post("/signals")
    async def ingest(signal: IntentSignal):
        customer = app.state.repository.customer(signal.customer_id)
        try:
            app.state.companion.intent_engine.validate_signal(customer, signal)
        except Abstain as exc:
            raise HTTPException(422, str(exc)) from exc
        created = app.state.repository.add_signal(signal)
        return {"event_id": signal.event_id, "status": "created" if created else "duplicate"}

    @router.post("/intents/detect", response_model=DetectionResponse)
    async def detect(body: DetectRequest):
        try:
            intent = app.state.companion.intent_engine.detect(body.customer_id, body.signal_ids)
            return DetectionResponse(status="ready", intent=intent)
        except Abstain as exc:
            return DetectionResponse(status="abstained", abstention_reasons=[str(exc)])

    @router.get("/customers/{customer_id}", response_model=CustomerContext)
    async def customer(customer_id: str):
        return app.state.repository.customer(customer_id)

    @router.get("/customers/{customer_id}/preferences")
    async def preferences(customer_id: str):
        customer = app.state.repository.customer(customer_id)
        return {
            "preferences": customer.stated_preferences,
            "suppressed_preferences": customer.suppressed_preferences,
            "consent": customer.consent,
        }

    @router.post("/customers/{customer_id}/preferences/remove", response_model=CustomerContext)
    async def remove(customer_id: str, body: RemovePreference):
        return app.state.customers.remove(customer_id, body.preference)

    @router.put("/customers/{customer_id}/preferences", response_model=CustomerContext)
    async def replace(customer_id: str, body: PreferencesRequest):
        return app.state.customers.replace(customer_id, body.preferences)

    @router.put("/customers/{customer_id}/consent", response_model=CustomerContext)
    async def consent(customer_id: str, body: Consent):
        customer = app.state.repository.customer(customer_id)
        customer.consent = body
        app.state.repository.save_customer(customer)
        return customer

    @router.post("/companion", response_model=CompanionExperience)
    async def companion(body: CompanionRequest):
        return await app.state.companion.run(body.customer_id, body.intent_id)

    router.include_router(routes(app))
    app.include_router(router)
    app.include_router(router, prefix="/api", include_in_schema=False)

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/app/")

    dist = ROOT / "frontend/dist"
    if dist.exists():
        app.mount("/app", StaticFiles(directory=dist, html=True), name="companion")
    return app


app = create_app()

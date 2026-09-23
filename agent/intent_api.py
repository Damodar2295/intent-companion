"""Phase 4 endpoints. No discovery or SearchPlan generation occurs here."""

from fastapi import APIRouter, HTTPException
from pydantic import Field, JsonValue

from agent.domain import Consent, IntentContext, IntentSignal, Model
from agent.intent_extraction import SignalDraft
from agent.repositories import Abstain


class IntentDetectionRequest(Model):
    customer_id: str = Field(min_length=1, max_length=100)
    signal_ids: list[str] | None = Field(default=None, max_length=200)
    debug: bool = False


class IntentDetectionResponse(Model):
    status: str
    intent: IntentContext | None = None
    abstention_reasons: list[str] = Field(default_factory=list)
    debug: dict[str, JsonValue] | None = None


class IntentExtractionRequest(Model):
    customer_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=3, max_length=1500)
    consent: Consent = Field(default_factory=Consent)


def intent_routes(app):
    router = APIRouter(prefix="/api/v1/intent", tags=["Intent v1"])

    @router.post("/signals")
    async def ingest(signal: IntentSignal):
        try:
            created = app.state.intents.ingest(signal)
        except Abstain as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"event_id": signal.event_id, "status": "created" if created else "duplicate"}

    @router.post("/detect", response_model=IntentDetectionResponse, response_model_exclude_none=True)
    async def detect(body: IntentDetectionRequest):
        try:
            intent = app.state.intents.detect(body.customer_id, body.signal_ids)
            return IntentDetectionResponse(
                status="ready", intent=intent, debug=app.state.intents.diagnostics(intent) if body.debug else None
            )
        except Abstain as exc:
            return IntentDetectionResponse(status="abstained", abstention_reasons=[str(exc)])

    @router.post("/extract", response_model=SignalDraft)
    async def extract(body: IntentExtractionRequest):
        customer = app.state.repository.customer(body.customer_id)
        if not customer.consent.allowed or not body.consent.allowed:
            raise HTTPException(422, "Personalization consent is missing or withdrawn.")
        draft = await app.state.intent_extractor.extract(body.text)
        # Consent may be withdrawn while an asynchronous model invocation is in flight.
        if not app.state.repository.customer(body.customer_id).consent.allowed:
            raise HTTPException(422, "Personalization consent was withdrawn during extraction.")
        return draft

    return router

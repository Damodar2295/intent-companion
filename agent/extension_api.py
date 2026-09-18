"""Additional routes keep the original consumer API compatible."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field

from agent import feedback
from agent.business.models import BusinessSignal, SpendCategory
from agent.domain import Consent, Model
from agent.merchant import MerchantRequest, resolve
from agent.repositories import Abstain, NotFound


class BusinessDetect(Model):
    business_id: str
    goal_id: str
    signal_ids: list[str] | None = None


class BusinessGenerate(Model):
    business_id: str
    intent_id: str


class Priorities(Model):
    priorities: list[SpendCategory] = Field(max_length=6)


class FeedbackRequest(Model):
    owner_id: str
    action: Literal["confirm", "dismiss", "restore"]


class ExtractRequest(Model):
    business_id: str
    text: str = Field(min_length=1, max_length=2000)


def routes(app):
    router = APIRouter()

    @router.get("/business/scenarios")
    async def scenarios():
        selections = {s["key"]: s["signal_ids"] for s in app.state.extensions.all("business_selection")}
        return [
            s.model_copy(update={"signal_ids": selections.get(s.business_id + ":" + s.goal_id, s.signal_ids)})
            for s in app.state.extensions.scenarios
        ]

    @router.get("/businesses/{business_id}")
    async def profile(business_id: str):
        return app.state.extensions.business(business_id)

    @router.put("/businesses/{business_id}/preferences")
    async def preferences(business_id: str, body: Priorities):
        profile = app.state.extensions.business(business_id)
        profile.priorities = sorted(set(body.priorities))
        app.state.extensions.put("business", business_id, profile.model_dump(mode="json"))
        return profile

    @router.put("/businesses/{business_id}/consent")
    async def consent(business_id: str, body: Consent):
        profile = app.state.extensions.business(business_id)
        profile.consent = body
        app.state.extensions.put("business", business_id, profile.model_dump(mode="json"))
        return profile

    @router.post("/business/signals")
    async def ingest(body: BusinessSignal):
        profile = app.state.extensions.business(body.business_id)
        try:
            app.state.business.engine.validate(profile, body)
        except Abstain as exc:
            raise HTTPException(422, str(exc)) from exc
        created = app.state.extensions.add_signal(body)
        return {"status": "created" if created else "duplicate", "event_id": body.event_id}

    @router.post("/business/intents/detect")
    async def detect(body: BusinessDetect):
        try:
            intent = app.state.business.engine.detect(body.business_id, body.goal_id, body.signal_ids)
            key = body.business_id + ":" + body.goal_id
            app.state.extensions.put("business_selection", key, {"key": key, "signal_ids": intent.signal_ids})
            return {"status": "ready", "intent": intent, "abstention_reasons": []}
        except Abstain as exc:
            return {"status": "abstained", "intent": None, "abstention_reasons": [str(exc)]}

    @router.get("/business/intents/{intent_id}/signals")
    async def signals(intent_id: str, business_id: str):
        intent = app.state.extensions.intent(intent_id)
        if intent.business_id != business_id:
            raise NotFound("Unknown intent for this business")
        return [app.state.extensions.get("business_signal", i) for i in intent.signal_ids]

    @router.post("/business/companion")
    async def companion(body: BusinessGenerate):
        return await app.state.business.run(body.business_id, body.intent_id)

    @router.post("/merchant/resolve")
    async def merchant(body: MerchantRequest):
        try:
            return resolve(body, app.state.repository, app.state.extensions, app.state.settings)
        except Abstain as exc:
            return {"status": "abstained", "message": str(exc), "accepted_products": [], "offers": []}

    def owned_intent(intent_id, owner, business=False):
        intent = app.state.extensions.intent(intent_id) if business else app.state.repository.intent(intent_id)
        if (intent.business_id if business else intent.customer_id) != owner:
            raise NotFound("Unknown intent for this owner")
        return intent

    @router.get("/intents/{intent_id}/feedback")
    async def consumer_status(intent_id: str, owner_id: str):
        intent = owned_intent(intent_id, owner_id)
        return {"status": feedback.status(app.state.repository, feedback.consumer_key(intent))}

    @router.post("/intents/{intent_id}/feedback")
    async def consumer_feedback(intent_id: str, body: FeedbackRequest):
        intent = owned_intent(intent_id, body.owner_id)
        return {"status": feedback.save(app.state.repository, feedback.consumer_key(intent), body.action)}

    @router.post("/business/intents/{intent_id}/feedback")
    async def business_feedback(intent_id: str, body: FeedbackRequest):
        intent = owned_intent(intent_id, body.owner_id, True)
        return {"status": feedback.save(app.state.repository, feedback.business_key(intent), body.action)}

    @router.post("/business/goals/extract")
    async def extract(body: ExtractRequest):
        profile = app.state.extensions.business(body.business_id)
        if not profile.consent.allowed:
            raise HTTPException(422, "Personalization consent is missing or withdrawn.")
        return await app.state.goal_extractor.extract(body.text)

    return router

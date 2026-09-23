from fastapi import APIRouter, HTTPException

from agent.context.models import ContextRequest, ContextResponse
from agent.outing.persistence import context_version


def context_routes(app):
    router = APIRouter(prefix="/api/v1/context", tags=["Context v1"])

    @router.post("/build", response_model=ContextResponse)
    async def build(body: ContextRequest):
        customer = app.state.repository.customer(body.customer_id)
        if not customer.consent.allowed or not body.consent.allowed:
            raise HTTPException(403, "Personalization consent is missing or withdrawn.")
        snapshot = context_version(customer)
        result = app.state.context_builder.build(body)
        current = app.state.repository.customer(body.customer_id)
        if not current.consent.allowed:
            raise HTTPException(403, "Personalization consent was withdrawn during context construction.")
        if context_version(current) != snapshot:
            raise HTTPException(409, "Preferences changed during context construction; start again.")
        return result

    return router

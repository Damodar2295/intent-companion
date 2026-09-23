"""Read-only index diagnostics; no filesystem paths or customer input accepted."""

import sqlite3

from fastapi import APIRouter, HTTPException


def index_routes(app):
    router = APIRouter()

    @router.get("/infrastructure/index")
    async def index_stats():
        try:
            stats = await app.state.ingestion.store.stats()
        except sqlite3.Error:
            raise HTTPException(503, "Retrieval index unavailable") from None
        return stats | {"embedding_mode": app.state.settings.embedding_mode, "customer_retrieval_enabled": False}

    return router


def retrieval_routes(app):
    from agent.outing.persistence import context_version
    from agent.retrieval.models import RetrievalRequest, RetrievalResponse

    router = APIRouter(prefix="/api/v1/retrieval", tags=["Retrieval v1"])

    @router.post("/search", response_model=RetrievalResponse, response_model_exclude_none=True)
    async def search(body: RetrievalRequest):
        repository = app.state.repository
        customer = repository.customer(body.customer_id)
        if not customer.consent.allowed or not body.consent.allowed:
            raise HTTPException(403, "Personalization consent is missing or withdrawn.")
        context = context_version(customer)
        result = await app.state.retriever.search(body, customer.market)
        current = repository.customer(body.customer_id)
        if not current.consent.allowed:
            raise HTTPException(403, "Personalization consent was withdrawn during retrieval.")
        if context_version(current) != context:
            raise HTTPException(409, "Preferences changed during retrieval; start again.")
        return result

    return router

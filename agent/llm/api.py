from fastapi import APIRouter


def llm_routes(app):
    router = APIRouter(prefix="/api/v1/llm", tags=["LLM v1"])

    @router.get("/routes")
    async def routes():
        gateway = app.state.llm_gateway
        return {
            "operations": gateway.router.describe(),
            "adapters": sorted(gateway.adapters),
            "gateway": "configured",
            "secrets_exposed": False,
        }

    return router

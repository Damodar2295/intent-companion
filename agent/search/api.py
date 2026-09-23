from fastapi import APIRouter, Request

from agent.search.models import SearchPlanRequest, SearchPlanResponse


def search_routes(app):
    router = APIRouter(prefix="/api/v1/search", tags=["Search v1"])

    @router.post("/plan", response_model=SearchPlanResponse)
    async def plan(body: SearchPlanRequest):
        return await app.state.search_planner.plan(body)

    from agent.tools.http import execute_connected
    from agent.tools.models import ExecutionResult

    @router.post("/execute", response_model=ExecutionResult)
    async def execute(body: SearchPlanRequest, request: Request):
        return await execute_connected(app.state.tool_orchestrator, body, request)

    return router

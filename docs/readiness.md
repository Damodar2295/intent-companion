# Phase 19: deployment readiness

`GET /api/readiness` reports whether the application is initialized and whether the configured outing LLM capability is available. It returns only `ready` or `degraded`, boolean checks, and demo/realtime mode; secrets and provider keys are never returned. The existing `/api/health` contract remains unchanged.

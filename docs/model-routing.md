# Phase 10: model routing

The application’s logical model operations are routed through the existing `LLMGateway` and `ModelRouter`. Supported operations include intent extraction, recommendation ranking, business goal extraction, search requirements/outing interpretation and grounded explanation. Each operation has a logical capability class (`lightweight` or `standard`) and a configured adapter/model route.

`GET /api/v1/llm/routes` exposes safe diagnostics: operation names, adapter labels, capability classes and whether a model is configured. It never returns keys, endpoints, deployment identifiers or prompt content. The endpoint is operational metadata, not a customer data API.

Configuration remains externalized through `LLM_ROUTES_JSON`, `LLM_GATEWAY_MODE`, existing LLM settings and outing model settings. Unknown operations, unavailable adapters and invalid route overrides fail at composition; there is no silent public-provider or mock fallback. Explicit mock mode routes all operations to the mock adapter. Search planning retains its Phase 5 rule that realtime cannot use a mock route. Business services continue to depend on the gateway interface, not provider SDKs.

The router’s `resolve` method enforces an operation’s configured capability class when callers request one. The gateway logs only operation, adapter, capability, latency and safe token/cost data. Model output remains schema-validated by the gateway; eligibility, evidence and monetary values remain deterministic application responsibilities.

This phase adds no new model provider, enterprise SDK, model deployment identifier, prompt strategy or customer-facing generated response. SafeChain/Astra remains an adapter seam to be supplied by the internal environment. The test suite verifies route isolation, capability mismatch rejection, explicit mock routing, missing-adapter failure and secret-free diagnostics.

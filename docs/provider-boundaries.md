# Service and provider boundaries — Phase 1

`agent.initialize` constructs one LLMGateway and injects it into consumer ranking, business goal extraction and outing language services. `agent.providers.container` owns concrete adapter selection. Compatibility constructors remain available for isolated service tests. Domain services retain evidence validation, eligibility, arithmetic and deterministic fallback decisions.

## Model operations and configuration

| Operation | Default adapter | Model source | Logical class |
|---|---|---|---|
| recommendation.ranking | chat | LLM_MODEL | standard |
| business.goal_extraction | chat | LLM_MODEL | lightweight |
| intent.entity_extraction | chat (Phase 4 opt-in) | LLM_MODEL | lightweight |
| search.plan_generation | responses | OPENAI_MODEL | lightweight |
| recommendation.explanation | responses | OPENAI_MODEL | standard |

Legacy `AI_PROVIDER=deterministic` stays the default; `llm` enables the existing consumer and business model paths. Demo outings use deterministic demo providers. Realtime interpretation requires OPENAI_API_KEY and OPENAI_MODEL. Missing realtime configuration remains an actionable error; it never substitutes synthetic discovery. Legacy model failures retain their existing deterministic fallback.

`LLM_GATEWAY_MODE=configured` preserves those choices. `LLM_ROUTES_JSON` optionally overrides adapter, model and model_class per operation. Unknown operations or unavailable adapters fail configuration. `mock` routes model invocations exclusively to MockLLMAdapter: tests must inject explicit handlers through build_gateway(mock_handlers=...). Missing fixtures fail explicitly rather than fabricating output. Demo behavior itself does not require mock model fixtures.

Chat uses LLM_ENDPOINT, LLM_API_KEY and LLM_TIMEOUT_SECONDS. Responses uses OPENAI_RESPONSES_ENDPOINT, OPENAI_API_KEY and the existing bounded outing transport, including retries, concurrency and timeouts. Endpoints require HTTPS except localhost development. Cancellation propagates through async calls. No new public provider is introduced.

Every gateway request contains operation, messages, a Pydantic response schema, optional logical model class and metadata. Results carry validated output, selected route, latency and available token usage. Arbitrary metadata, prompts, credentials and raw outputs are not logged. Estimated costs are logged only for configured OUTING_LLM_PRICE_TABLE entries. Response schema validation does not replace domain checks: candidate IDs, exact source excerpts and permitted evidence references are still checked by services before use. Models cannot supply monetary calculations or eligibility.

## Enterprise / SafeChain contract

SafeChain is not a configured dependency and no enterprise endpoint or SDK invocation is supplied. Selecting `safechain` as gateway mode or adapter fails; it cannot silently route to a public model provider.

An enterprise integration must implement async `LLMAdapter.invoke(LLMRequest, ModelRoute) -> AdapterOutput`. It must translate the request schema and messages to the approved SDK, return structured JSON content plus available token counts, propagate cancellation, enforce bounded timeouts, and convert provider failures to safe LLMError messages without credentials or customer content. Authentication, approved deployment identifiers and SDK loading belong inside that adapter. Operators must supply these real integration details, install the approved dependency and register the adapter and operation routes in the composition root. Contract tests must cover malformed output, missing configuration, cancellation and absence of public-provider fallback before activation. This is a documented extension contract, not a working SafeChain adapter.

## Catalog and discovery

Cards, benefits, offers, rewards and merchants have provider protocols backed by SQLiteCatalogProvider. Existing market/segment/destination filtering remains unchanged. Places, events, web discovery and routing reuse existing outing protocols and implementations. OutingService accepts injected dependencies; selection occurs at composition. AMEX experiences explicitly raise CapabilityUnavailable and supply no invented inventory. Existing evidence freshness, storage restrictions and synthetic AMEX labels are unchanged.

## Retrieval contracts, not runtime retrieval

VectorStore, EmbeddingService and RerankerService describe future boundaries. The `agent.retrieval.testing` implementations use hashed tokens, dot products and token overlap solely for deterministic tests. They are not genuine semantic embeddings or semantic rerankers, have no quality claims and are not wired into customer runtime. No database migration, vector infrastructure, ingestion, hybrid retrieval or semantic cache is introduced.

## Verification scope

Backend tests use mocked transports and isolated SQLite storage. Postman tests replay collection requests and execute their JavaScript assertions. These checks establish compatibility and boundary behavior, not live-provider availability. No live credentials or SafeChain deployment were exercised in Phase 1.

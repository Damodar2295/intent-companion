# Architecture and implementation decisions

This adapts the copied FastAPI / React / LangGraph boilerplate into a modular monolith. The original reference project is untouched. CRM, autonomous tool loops, embedding retrieval, enterprise deployment templates and their unrelated tests are removed from the copied app. Its application initialization, factory and graph boundaries remain.

Runtime: Python 3.11+, FastAPI, Pydantic v2, LangGraph fixed workflow, SQLite; React 19 + TypeScript + Vite. SQLite replaces vector retrieval because the authoritative synthetic catalog is structured. No live product facts, financial decisions, external submissions or customer data are used.

Implementation order: contracts and seed fixtures → repositories → consent and intent → catalog matching and value calculation → guarded AI adapter and graph → API and frontend → tests and documentation.

The graph runs guard → retrieve/filter → calculate → rank → compose. There are no agent loops or side-effectful model tools. Detection is a separately callable service before experience generation. A stored intent is revalidated against current consent, signal expiry and preference suppression at activation time.

Domain models live in agent/domain.py. Services in agent/intent_engine.py, customer_context.py, matching.py and value_calculation.py depend on repository interfaces. agent/ai.py validates model choices; agent/llm owns model transports and structured-output validation. agent/orchestration.py carries evidence through the graph. agent/main.py exposes thin routes; initialize.py and factory.py construct and close dependencies.

Catalog facts, acceptance, rule outcomes and Decimal value calculations never come from the LLM. Only existing candidate and evidence IDs can cross back from that boundary. Deterministic rendering supplies all factual wording. Unavailable or invalid AI returns the same safe deterministic experience, labeled with a fallback reason.

SQLite stores customers, signals, intents, typed catalog records and audit experiences. JSON fixtures under data are versioned synthetic sources; startup inserts once and never overwrites preferences. Evidence snapshots remain auditable after catalog edits. No request/profile bodies or model secrets are logged. This is a localhost-only single-user demo, not an authenticated multi-tenant service.

## Bounded outing workflow

The new `agent/outing` package operates alongside the original companion graph. It provides field evidence, provider adapters, deterministic identity/verification/planning, synthetic enrichment, expiring run retrieval and fetch-SSE progress. `agent.initialize` owns its lifecycle; `agent.main` registers additive routes. The business workflow and legacy value calculator remain unchanged. See [the outing architecture](outing.md#data-flow) for provider boundaries, storage choices and ranking policy.

## Phase 1 service boundaries

All three model consumers share the application-scoped LLMGateway. The provider composition root selects adapters and injects dependencies; domain services retain eligibility, exact evidence-reference checks and deterministic fallbacks. SQLite catalog access is wrapped without changing filtering. Retrieval contracts and explicitly labeled test doubles are not connected to customer runtime. See [provider boundaries](provider-boundaries.md) for configuration and enterprise integration requirements.

## Phase 2 canonical models

`agent.canonical` exports the existing consumer and outing models plus typed Source, Place, Event and AmexExperience records. Synthetic fixture provenance and cross-record references can be checked independently with `python -m scripts.validate_seeds`. The new knowledge bundle remains seed-only; runtime retrieval and storage are unchanged. See [canonical models](canonical-models.md).

## Phase 3 vector ingestion

`agent.retrieval.documents` normalizes typed synthetic inputs into bounded searchable records. `IngestionService` embeds changed documents through EmbeddingService and atomically publishes through IngestionStore. The local SQLiteVectorStore persists vectors, metadata, content versions and FTS5 entries. Embeddings remain disabled by default; openai mode adds a configured real embedding adapter, while explicit test_hash mode is non-semantic and never a realtime fallback. Customer retrieval is unchanged. See [storage decision, commands and limits](vector-ingestion.md).

## Phase 4 intent classification

IntentService shares IntentEngine's consent, aggregation and expiry implementation while extending classification beyond the legacy Rome travel boundary. Versioned intent endpoints expose structured ingestion, classification/debug and permission-gated draft extraction. The optional `intent.entity_extraction` operation uses the existing shared LLMGateway; classification and confidence remain deterministic. See [Phase 4 behavior and limitations](intent-service.md).

### Phase 5 search planning boundary

`agent/search` converts text into validated requirements using the shared gateway operation `search.requirements_generation`. Deterministic quote and constraint validation wraps the existing outing SearchPlan model; current consent/preferences remain authoritative. Plans are not persisted, and no discovery/routing/value services run here. The existing outing interpretation operation remains compatible. See [Search planning](search-plan.md).

### Phase 6 tool execution boundary

`agent/tools` selects fixed injected providers from validated search requirements, runs independent calls concurrently, enforces per-tool/run deadlines and records safe traces. Composition reuses existing provider adapters and structured SQLite catalogs. Routing is explicitly deferred until verified ordered stops exist; hybrid retrieval and later planning remain outside this stage. [Details](tool-orchestration.md).

### Phase 7 retrieval boundary

`agent/retrieval/hybrid.py` composes the existing SQLite FTS5 and vector interfaces. Metadata predicates run before channel results are merged with RRF; semantic, lexical and fused scores remain distinct. The endpoint returns retrieval candidates only. Reranking and acceptance belong to Phase 8. See [Hybrid retrieval](hybrid-retrieval.md).

### Phase 8 ranking boundary

Reranking is injected after hybrid RRF retrieval and before later business validation. `RerankerService` may be replaced by an approved enterprise adapter; the local token-overlap implementation is test-only. Threshold decisions remain separate from eligibility and monetary calculations. See [Reranking](reranking.md).

### Phase 9 context boundary

`agent/context` owns deterministic evidence-aware context construction and token estimates. It is a preparation layer for later grounded generation, with no provider calls, persistence or business calculations. See [Context engineering](context-engineering.md).

### Phase 10 model routing boundary

`ModelRouter` maps logical operations to configured capability classes and adapters. `LLMGateway` remains the only model invocation boundary; route diagnostics are safe and read-only. No provider SDK or enterprise deployment is invented. See [Model routing](model-routing.md).

### Phase 12 value boundary

Merchant resolution and AMEX enrichment remain deterministic. Branch corroboration is required; event/venue/ticket identities are not merged. Synthetic matches carry explicit labels and conservative stacking semantics. See [Merchant/value matching](merchant-value.md).

### Phase 13 planner boundary

The validated outing service now has a JSON plan projection in addition to SSE. Scheduling reuses verified facts, route feasibility, opening-hour checks and conservative synthetic value enrichment. Editable mutations remain outside this phase. See [Outing planner](outing-planner.md).

### Phase 14 edit boundary

Edits operate on short-lived validated plans and mark results for revalidation. Client-provided stops never bypass discovery/verification. See [Editable outings](editable-outing.md).

# API

Base URL: `http://127.0.0.1:8090`. The same endpoints are also mounted under `/api` for the frontend. Interactive typed schemas: `/docs`; machine-readable schema: `/openapi.json`.

| Method | Route | Input / result |
| --- | --- | --- |
| GET | `/health` | Readiness, configured provider, synthetic/demo indicators and clock. |
| GET | `/scenarios` | Three scenario IDs, titles, customer IDs and signal IDs. |
| POST | `/signals` | IntentSignal → created/duplicate event ID. Invalid or unpermissioned signals are not stored. |
| POST | `/intents/detect` | `{customer_id, signal_ids?}` → status, typed intent or abstention reasons. Omit IDs to use all stored signals for that customer. |
| GET | `/customers/{id}` | Current synthetic customer profile. |
| GET | `/customers/{id}/preferences` | Stated preferences, suppression list and consent. |
| POST | `/customers/{id}/preferences/remove` | `{preference}` → updated profile; idempotently suppresses the tag. |
| PUT | `/customers/{id}/preferences` | `{preferences:[...]}` → replaces active preferences and suppresses removed historical tags. |
| PUT | `/customers/{id}/consent` | `{allowed, purpose:"personalization"}` → updated profile. Additional demo privacy control. |
| POST | `/companion` | `{customer_id, intent_id}` → CompanionExperience. Always revalidates ownership, current consent and preferences. |

Errors: 404 unknown IDs or wrong-customer intent/signal; 409 event-ID/content conflict; 422 malformed request or disallowed ingestion; 503 health not ready; redacted 500 unexpected failure. A valid generation/detection request with insufficient evidence returns 200 and `status:"abstained"`, not invented results. Responses include `X-Request-ID`, `X-Response-Time-Ms`, and `Cache-Control: no-store`.

## Example flow

```sh
curl http://127.0.0.1:8090/health
curl -X POST http://127.0.0.1:8090/intents/detect \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"cust-dining","signal_ids":["evt-2-1","evt-2-2","evt-2-3"]}'
```

Detection response excerpt (generated ID varies):

```json
{"status":"ready","intent":{"intent_id":"intent-<generated>","destination":"Rome","start_date":"2026-10-10","end_date":"2026-10-15","confidence":0.95,"intent_stage":"planning","preferences":["fine dining","museums"]},"abstention_reasons":[]}
```

Copy the returned intent ID into the next request:

```sh
curl -X POST http://127.0.0.1:8090/companion \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"cust-dining","intent_id":"intent-<generated>"}'
```

Experience response excerpt (the actual response includes full evidence and all recommendation groups):

```json
{
  "status": "ready",
  "provider_mode": "deterministic",
  "preferences_used": ["fine dining", "museums"],
  "value_summary": [{"product_id":"card-a","totals_by_currency":{"USD":"60.00"}}],
  "synthetic": true
}
```

```sh
curl -X POST http://127.0.0.1:8090/customers/cust-dining/preferences/remove \
  -H 'Content-Type: application/json' -d '{"preference":"fine dining"}'
```

Reusing the same intent ID now generates museum-oriented recommendations without the removed tag. Turning consent off using its PUT endpoint makes that same companion request return `status:"abstained"` with empty recommendation/value groups.

## Signal example

```json
{
  "event_id":"evt-new-booking",
  "customer_id":"cust-dining",
  "source":"synthetic-demo",
  "event_type":"travel_booking",
  "timestamp":"2026-09-17T11:00:00Z",
  "consent":{"allowed":true,"purpose":"personalization"},
  "context":{"origin":"JFK","destination":"Rome","start_date":"2026-10-10","end_date":"2026-10-15","purpose":"leisure","preferences":[]},
  "synthetic":true
}
```

## Additive outing endpoints

`GET /api/outing/capabilities`, `POST /api/outings/stream` (JSON POST with SSE response), and `GET /api/outings/{id}` run the separate consumer outing workflow. Existing endpoints are unchanged. See [outing API and policies](outing.md#api) for schemas, events, consent, expiry and configuration errors.

## Executable API examples

[Postman collection](../postman/IntentCompanion.postman_collection.json) covers the existing `/api` routes, including consent, preferences, errors and outing SSE. Follow [isolated demo instructions](../postman/README.md). No `/api/v1` endpoints were added in Phase 1.

## Phase 3 index diagnostics

`GET /api/infrastructure/index` returns persisted record counts by type, embedding-space information, last index-write time and explicit test/activation labels. An empty index is valid; unavailable storage returns 503. No credentials or database paths are returned. See [ingestion operations](vector-ingestion.md) and the Postman Infrastructure folder. This read-only API does not trigger embeddings or read seed JSON.

## Phase 4 intent APIs

The implemented versioned routes are `POST /api/v1/intent/signals`, `POST /api/v1/intent/detect` and `POST /api/v1/intent/extract`. See [schemas, examples and deterministic confidence rules](intent-service.md). Detection optionally accepts `debug: true`. Extraction requires explicit request consent and returns a review-only draft; it does not store a signal. Postman includes positive and negative assertions for these routes. Other proposed `/api/v1` capabilities remain unimplemented.

### Search requirements (Phase 5)

`POST /api/v1/search/plan` accepts consented text plus optional destination/schedule/budget/origin constraints. Returns `READY` requirements or `CLARIFICATION_REQUIRED`; it does not execute discovery or calculate benefits. See [request, configuration and failure semantics](search-plan.md). Existing outing POST-SSE remains unchanged.

### Tool execution (Phase 6)

`POST /api/v1/search/execute` accepts the Phase 5 planning request and returns bounded discovery/catalog outputs with invocation traces. Clarification invokes no discovery tools; provider failures can return PARTIAL. See [selection, limits and status semantics](tool-orchestration.md). This JSON endpoint does not produce an itinerary or calculate AMEX value.

### Hybrid retrieval (Phase 7)

`POST /api/v1/retrieval/search` applies metadata/freshness filters, runs lexical and configured semantic retrieval, and returns RRF-merged typed candidates with optional debug diagnostics. It does not rerank or evaluate eligibility. See [hybrid retrieval](hybrid-retrieval.md).

### Reranking and retrieval acceptance (Phase 8)

The retrieval endpoint now optionally applies an injected reranker after RRF. Responses keep lexical, semantic, RRF and reranker scores separate and report threshold decisions. These are retrieval acceptance labels, not eligibility or savings decisions. See [reranking](reranking.md).

### Context building (Phase 9)

`POST /api/v1/context/build` applies explicit evidence selection, conversation pruning and token budgeting. It returns a bounded context package with optional compression diagnostics. It does not invoke a model or generate customer prose. See [context engineering](context-engineering.md).

### Model routing (Phase 10)

`GET /api/v1/llm/routes` returns safe configured logical operation routes and adapter availability. It omits credentials, endpoints and deployment identifiers. All generative operations continue through `LLMGateway`. See [model routing](model-routing.md).

### Provider capabilities (Phase 11)

`GET /api/v1/providers/capabilities` reports configured web, event, place, route and AMEX-experience capabilities plus freshness policies without secrets. Existing outing capabilities and SSE routes remain unchanged. See [provider integrations](provider-integrations.md).

### Merchant/value preview (Phase 12)

`POST /api/v1/value/preview` applies deterministic branch identity and synthetic catalog enrichment to one verified entity and selected card. It returns explicit illustrative labels and separate points/currencies. See [merchant and value matching](merchant-value.md).

### JSON outing planning (Phase 13)

`POST /api/v1/outings/plan` returns a validated multi-alternative outing plan using the existing provider, verification, routing and enrichment pipeline. The SSE `/outings/stream` route remains available. Editable outing operations are deferred to Phase 14. See [outing planner](outing-planner.md).

### Editable outings (Phase 14)

`POST /api/v1/outings/{id}/edit` supports bounded removal and constraint/category edits on short-lived outing plans. New stops require a fresh verified plan and are rejected. See [editable outings](editable-outing.md).

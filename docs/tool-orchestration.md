# Phase 6: bounded tool orchestration

`POST /api/v1/search/execute` accepts the same body as `/api/v1/search/plan`. The server creates a validated Phase 5 SearchPlan, then selects a fixed set of injected tools. Client-supplied arbitrary tool names and forged plans are not accepted. Clarification returns immediately without discovery. This endpoint is separate from the existing outing POST-SSE and consumer/business workflows.

```json
{
  "customer_id": "cust-dining",
  "consent": {"allowed": true},
  "text": "Plan concert and dinner in Rome tomorrow at 6pm for three hours",
  "timezone": "Europe/Rome"
}
```

## Selection and scope

| Plan requirement | Selected tools |
|---|---|
| Outing with non-event categories | Places |
| Outing with EVENT | Events and web discovery |
| Outing with EXPERIENCE and AMEX value | AMEX experience inventory |
| AMEX value requested | Cards, benefits, offers, rewards |
| Outing plus AMEX value | Merchants as an additional catalog input |
| Routing required | Explicitly deferred until verified, ordered stops exist |

Benefits-only requests never call web, places, events or routing. Without a destination, catalog access queries only global records. The current seed has no global matches, so this may correctly return EMPTY. Supplying Rome finds the existing illustrative Rome catalog. Catalog access reuses structured SQLite providers; no JSON file reads, hybrid retrieval, RRF or reranking were added. Phase 7 remains separate.

Routing cannot safely use arbitrary discovery snippets as coordinates or invent a stop order. `deferred.routing` records that dependency; existing outing routing continues to work unchanged. Official-page expansion, factual verification, scheduling, eligibility and AMEX value calculation are not performed by this endpoint. No final recommendation or savings claim is generated.

## Execution and limits

Independent selected providers run concurrently under an application-wide semaphore. The registry is constructed at dependency injection; the orchestrator has no provider HTTP/authentication code. Demo places/events reuse explicitly fictional fixtures. Demo web is unavailable rather than a pretend search engine. AMEX experience inventory remains explicitly unavailable. Realtime composes the existing Places, Events and Brave adapters only when configured; missing providers return UNAVAILABLE and never fall back to demo.

Defaults, configurable in `.env`:

- `TOOL_CONCURRENCY=4` (1–8), shared across execution requests in one process.
- `TOOL_MAX_CALLS=10` (1–10), provider invocations per request, excluding the single planning step.
- `TOOL_TIMEOUT_SECONDS=8` (>0–30), per running provider invocation.
- `TOOL_RUN_DEADLINE_SECONDS=30` (>0–60), whole request including planning and queue time.
- `TOOL_RESULT_LIMIT=20` (1–100), output rows per tool; truncation is recorded.

No recursive agent loops or orchestration retries. Existing provider transports retain their bounded transient retries, covered by the invocation deadline. Fixed selection order determines result/trace order independently of completion order. Completed work survives provider failure or deadline expiry. Pending work is cancelled and awaited; caller cancellation and HTTP disconnect stop child tasks. Providers must honor asynchronous cancellation. In-process synchronous SQLite reads retain existing behavior and cannot be preempted mid-query.

## Response and traces

Responses include run_id, mode, planning, outputs, trace and deferred dependencies. Status is READY (nonempty successful discovery/catalog stage), EMPTY, PARTIAL, ERROR or CLARIFICATION_REQUIRED. READY does **not** mean a verified itinerary. Outputs are typed `DiscoveryCandidate` records labeled DISCOVERY_ONLY or typed existing synthetic catalog records labeled ILLUSTRATIVE_CATALOG_NOT_ELIGIBILITY. Invalid provider results are rejected, not exposed as arbitrary payloads. Search snippets remain without verified evidence. No totals are aggregated.

Every selected tool and the planning step has a trace: stable sequence, status, start/finish timestamps, queue and execution milliseconds, result count, truncation and a fixed safe message. Budget-skipped tools are explicitly marked SKIPPED; missing tools UNAVAILABLE. Safe JSON logs carry run_id and these metrics, excluding customer IDs, input text, coordinates, credentials and raw exception messages. Existing gateway/provider logs retain lower-level retry/token metrics; Phase 6 does not invent token or cost estimates.

Consent and preference context are rechecked before and after asynchronous operations and before return. Withdrawal returns 403; changed preferences return 409 and discard all collected outputs. Model failures retain the Phase 5 actionable 503 behavior. No execution result or precise origin is persisted; existing Cache-Control: no-store applies.

## Verification

`tests/test_tool_orchestration.py` covers deterministic selection, concurrent execution with a shared limit, missing providers, partial timeouts, queued task cancellation, invocation/result budgets, invalid output, privacy-safe logs, consent/preference changes, HTTP disconnects and absent realtime credentials. The Postman Phase 6 folder covers ordinary JSON discovery, catalog-only execution, unavailable demo web partial results, clarification, consent and invalid constraints. All external behavior is tested with injected fixtures; no live provider requests were made for Phase 6.

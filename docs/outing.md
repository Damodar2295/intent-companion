# Outing discovery: implementation and operating guide

The consumer app now includes **An outing, made for you**. Prospect, member, legacy merchant lookup, and small-business APIs remain available. No booking, payment, history collection, or email integration is implemented.

## Run locally

Use the existing installation and startup instructions in README. Open `/app/` on the backend or the Vite development address. The backend must remain bound to `127.0.0.1`. This prototype has no production authentication or tenant authorization; do not expose it publicly.

Default `.env.example` settings use explicit offline demonstration. Places, events, coordinates, routes, and merchant relationships in this mode are fictional. The Rome dataset is intentionally bounded; other cities return an explanatory partial result. The outing clock uses current UTC time, including for evidence expiry; `DEMO_NOW` still belongs to the legacy journey.

To enable real provider requests:

```dotenv
DEMO_MODE=false
REALTIME_MODE=true
OPENAI_API_KEY=...
OPENAI_MODEL=your-supported-model
SEARCH_API_KEY=...
PLACES_API_KEY=...
ROUTING_API_KEY=...
EVENT_API_KEY=...
AMEX_DATA_MODE=synthetic
```

Choose an OpenAI model that supports Responses structured outputs. No model is hardcoded. Enable Places API (New), Routes, Brave Search, and Ticketmaster Discovery for their respective keys. Both mode flags true or both false cause startup validation to fail. Missing OpenAI configuration returns HTTP 503 before streaming. Other absent providers produce explicit warnings and partial output. The legacy `AI_PROVIDER`/`LLM_*` ranking adapter is unchanged and independent.

The form requires a concrete date and destination timezone. Known destination names suggest a timezone; other names clear it so the user must supply an IANA timezone. Natural-language ambiguity or conflicts trigger clarification. Local times crossing midnight, nonexistent DST times, and ambiguous DST times are rejected; split such requests into separate outings. No hotel or other origin is invented. Location sharing is optional and user initiated.

## Data flow

`agent/outing` uses the existing Pydantic, HTTPX, SQLite and dependency-injection infrastructure. It does not replace the companion LangGraph workflow.

1. Interpret categories/preferences with strict Responses JSON schema and application validation. Explicit form date/time/location fields are authoritative. Removed preferences are filtered again after interpretation.
2. Discover through Places text search, Ticketmaster and Brave concurrently. Provider transports have a shared concurrency limit of four, configurable timeouts and no more than two transient retries.
3. Normalize provider identities. Names never deduplicate branches. Events can merge across providers only with corroborating name, address, coordinates and occurrence timestamp; conflicting field evidence is retained.
4. Verify individual fields against configurable authority, freshness and a minimum evidence-strength threshold. These scores are policy labels, not calibrated probabilities. Search snippets have no fact authority. Invalid, stale or low-confidence fields cannot enter verified facts. Equal-authority disagreements suppress the field.
5. Resolve merchant identity using exact trusted identifiers or corroborating branch name/address/website. Events remain separate from venues and ticket sellers. There are **no real merchant-to-offer mappings shipped**. Fictional identifiers and the explicit mapping fixture apply only to fictional entities.
6. Enrich from the existing synthetic catalog with selected-card eligibility, catalog age, offer dates, and individually confirmed conditions. All value says **Demo / illustrative AMEX value**. Prospect comparisons are hypothetical. No match means no merchant-specific value. The fixture catalog expires 30 days after its recorded verification by default; advancing the clock does not silently refresh it.
7. Filter feasibility, obtain routes, then use deterministic weighted ranking (30/20/20/15/10/5). Planning is a bounded greedy search over at most eight verified candidates, up to three distinct alternatives and four stops. It is not a global route optimizer. Closed/cancelled/unreachable stops are excluded. Unknown hours/prices or unknown event end times make feasibility incomplete. Unknown event duration is explicitly assumed. Routes are estimates, not live inventory or a reservation guarantee.
8. Explain only scheduled, verified facts. The model must reference supplied evidence IDs and choose from constrained customer wording; arbitrary generated factual prose is not accepted. Any explanation failure uses deterministic wording.

The selected card is evaluated independently. Switch cards and replan to compare another held card or hypothetical product. Totals are per alternative, not across alternatives. Explicit stacking groups select a single cash value in one currency, or points if there is no eligible cash alternative. Cash and points in the same exclusive group are not added together. Different currencies in one exclusive group are not compared; those candidates remain visible but unaggregated. No points-to-cash conversion is used. Unknown/non-stackable values and unconfirmed conditions stay outside totals. Changes to condition checkboxes require replanning.

## Official pages and storage

`OFFICIAL_SOURCE_HOSTS` is an exact comma-separated allowlist of operator-verified event organizer hosts. Empty by default. Only JSON-LD Events with a name, address, coordinates and timezone-qualified schedule are extracted. JavaScript rendering and arbitrary website crawling are not supported. Allowlisting must establish source authority; merely finding a domain in search is insufficient.

Official requests allow HTTPS/443 only, reject credentials and private/non-global addresses, pin a verified DNS address for the connection, retain hostname TLS verification, reject redirects, and cap HTML bodies at 512 KB. Page scripts are never executed.

SQLite receives an additive `outing_runs` metadata table. Provider evidence and relationship objects are held only in expiring memory, not persisted as raw Places data. Results expire at the earlier of five minutes and the earliest selected evidence/route/value expiry. Restarting the backend invalidates results even if metadata remains. Precise user origin coordinates are removed before retaining a run. Expiry timers evict retained results and run metadata; access/new runs also purge expired entries. This is deliberately stricter than generic persistent caching: no Places response cache is used. Only interpretation results and route estimates use bounded in-memory TTL caches. Google-derived evidence retains Google Maps attribution and provider links. Review provider terms before deploying or extending storage behavior.

Consent and preference snapshots are checked at each stage, before completion and at retrieval. A change clears results and stops further processing at the next check. Browser cancellation aborts the POST and cancels provider tasks. Requests are restricted to local browser origins and rate-limited per known customer to five starts/minute, with one active run. These controls are not a substitute for production authentication.

## API

- `GET /api/outing/capabilities`: mode and capability booleans; no keys or endpoint secrets.
- `POST /api/outings/stream`: JSON request, fetch-based SSE response.
- `GET /api/outings/{id}`: short-lived result, or 404 after expiry/context change/restart.

Example request:

```json
{
  "customer_id": "cust-dining",
  "text": "Find an evening event, dining and shopping in Rome",
  "city": "Rome",
  "date": "2026-10-02",
  "timezone": "Europe/Rome",
  "start_time": "17:00",
  "end_time": "23:00",
  "travel_mode": "WALK",
  "budget": "150",
  "currency": "EUR",
  "number_of_people": 1,
  "card_id": "card-a",
  "visit_minutes": 60,
  "confirmed_condition_ids": []
}
```

Optional `user_location` is `{ "lat": 41.9, "lng": 12.48 }`. It is never inferred from browsing or booking data. Condition identifiers come from returned matches; unconfirmed assumptions do not create savings.

Each SSE `data:` JSON frame contains `run_id`, monotonic `sequence`, `stage`, UTC `timestamp`, safe `message`, and optional final `result`. Stages include PLANNING, SEARCHING, VERIFYING, ENRICHING, EXPLAINING, then READY/PARTIAL/ERROR. Empty UI state precedes a run. The default 60-second deadline returns completed alternatives when available; it never substitutes synthetic records. Cancellation has no final result. A prematurely terminated stream becomes a visible UI error.

## Policies and observability

Defaults: route/availability five minutes, opening status one hour, hours/event schedule six hours. `OUTING_TTL_POLICY`, `OUTING_SOURCE_PRIORITY`, and `OUTING_FIELD_SOURCE_PRIORITY` can override policies. Field overrides replace the allowed authority map for that field. Never extend provider storage permissions using a TTL override. `OUTING_RANKING_WEIGHTS` requires all six signals summing to one.

Logs contain run/stage timing, provider success/failure, retry count, cache hits and OpenAI token usage. Raw user text, coordinates, credentials and provider payloads are excluded. Estimated model cost is null unless `OUTING_LLM_PRICE_TABLE` contains the configured model's input/output price per million tokens. Configure prices explicitly rather than relying on outdated built-in rates.

## Validation and live-test status

`tests/test_outing.py` covers demo and mocked realtime composition, provenance conflicts, stale hours, branch identity, no synthetic fallback, routing failure, transient retries, route-cache identities, cancellation, consent changes, deadlines, SSE API, SSRF, currencies/points and conservative value conditions. Frontend tests cover progress/results, cancellation, consent withdrawal, provider errors and fragmented SSE transport.

The mocked realtime end-to-end test exercises HTTPX transports for OpenAI Responses, Brave, Google Places, Google Routes and Ticketmaster. These are **not credential-enabled smoke tests**. No live API credentials were available during implementation, so no real provider success or real venue inventory has been claimed. Run `python scripts/smoke_outing.py --date YYYY-MM-DD` after configuring credentials to exercise the live adapters. It reports which provider-derived sources/routes reached a completed result; partial results require inspection.

Existing tests cover legacy prospect/member, preference, merchant lookup and business flows. Continue using mocked transports in CI. The remaining launch gate is a credential-enabled smoke test with provider accounts and billing configured; public hosting additionally requires authentication and access controls.

### Reviewed merchant mappings

`OUTING_MERCHANT_MAPPINGS` optionally accepts a JSON list of reviewed `{merchant_id, place_id}` records, or `{merchant_id, names, address, website}` records. The merchant ID must correspond to the illustrative catalog. The latter requires all branch corroborators; a name or model similarity alone is insufficient. These are operator assertions of branch identity, not proof of a genuine AMEX partnership. No realtime mappings ship by default. Any resulting enrichment still carries the synthetic label, catalog verification date, validity, selected-product conditions and explicit source evidence.

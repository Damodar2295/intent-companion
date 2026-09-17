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

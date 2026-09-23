# Phase 15: grounded outing responses

`GET /api/v1/outings/{id}/response` projects the first available alternative into a customer-facing response using only stops with permitted evidence identifiers. It preserves the plan status and warnings, deduplicates evidence references, and never adds provider facts, prices, routes, or AMEX value.

The response is a bounded projection of the short-lived outing plan. Missing or expired plans return `404`; generated prose remains constrained by the existing explanation service and falls back to deterministic wording when the model is unavailable. This endpoint does not create new places, refresh stale provider data, or recalculate eligibility.

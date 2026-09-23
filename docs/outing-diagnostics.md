# Phase 17: safe outing diagnostics

`GET /api/v1/outings/{id}/diagnostics` returns bounded operational metadata for a short-lived outing run: status, mode, alternative and stop counts, evidence-reference count, warning count, and expiry. It deliberately excludes request text, coordinates, provider payloads, credentials, and customer preferences.

The endpoint follows the same consent, preference-version and expiry checks as plan retrieval. Missing or invalidated runs return `404`. Diagnostics support local demos and troubleshooting; they are not a provider-quality or statistical confidence score.

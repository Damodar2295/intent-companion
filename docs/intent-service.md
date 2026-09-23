# Phase 4 — consent-aware intent service

The versioned IntentService extends the existing deterministic IntentEngine. It supports travel, dining, event, shopping and lifestyle intent. Existing `/signals`, `/intents/detect`, `/api` aliases and their Rome travel behavior remain available. No frontend change, database migration, browser-history collection or new discovery workflow is introduced.

## API

| Method | Path | Behavior |
|---|---|---|
| POST | /api/v1/intent/signals | Normalize/validate a permissioned structured signal, then insert idempotently |
| POST | /api/v1/intent/detect | Classify and persist an IntentContext from selected signal IDs |
| POST | /api/v1/intent/extract | Produce a review-only entity draft; stores neither text nor a signal |

The versioned signal endpoint accepts the existing IntentSignal shape. `context.intent_type` is optional, and `event_booking` is now supported. Type normalization accepts case/whitespace, spaces/hyphens and existing aliases, including `event_reservation`. Destinations use the existing normalization, including Rome/Roma/FCO. Structured destinations beyond Rome are accepted as customer input; this does not verify a real place or imply catalog availability there.

Example signal:

```json
{
  "event_id": "demo-event-booking",
  "customer_id": "cust-dining",
  "source": "synthetic-user-input",
  "source_type": "SYNTHETIC",
  "event_type": "event_booking",
  "timestamp": "2026-09-17T10:00:00Z",
  "consent": {"allowed": true},
  "context": {
    "destination": "Paris",
    "start_date": "2026-10-10",
    "end_date": "2026-10-15",
    "purpose": "leisure",
    "preferences": ["culture"]
  }
}
```

The timestamp is for the configured demo clock; realtime callers must supply a current permissioned timestamp.

Detection:

```json
{
  "customer_id": "cust-dining",
  "signal_ids": ["demo-event-booking"],
  "debug": true
}
```

`ready` responses contain the stored intent. `abstained` responses explain missing consent, expired/future signals, ambiguous activity, incomplete dates or conflicting contexts. Unknown customer/signal ownership returns 404. Ingestion errors return 422; event-ID collisions with different content return 409. No signal gets persisted after a consent failure.

## Classification, stage and confidence

Travel/hotel signals imply travel; restaurant signals imply dining; event signals imply event. Generic declared/app/web/ad signals need `context.intent_type` or a more specific supporting signal. Explicit types conflicting with a specific signal type are rejected. Travel signals can aggregate supporting dining/events into a trip; mixed non-travel activity types produce lifestyle intent. Different destinations, incompatible dates or purposes are never silently merged. Select a coherent subset using signal_ids; selecting no IDs examines the existing customer signal set and may abstain if incompatible/stale signals are present.

A travel booking establishes booked travel, a restaurant booking booked dining, and an event booking booked event. A restaurant booking alone cannot establish booked travel. Other intents become planning when confidence reaches INTENT_PLANNING_THRESHOLD (default 0.4); otherwise they remain exploring. General lifestyle/shopping intents do not invent a booked state.

Confidence is `min(1, sum(configured weight for each unique signal type))`, rounded to four decimals. Repeated event IDs are deduplicated only if their contents agree. Different IDs of the same type contribute weight once in stable timestamp/ID order. The original weights remain unchanged; event_booking has weight 0.9. INTENT_WEIGHTS_JSON continues to override weights; both direct Settings and environment configuration validate known signal types and bounded values.

Debug output names the heuristic, marks it as non-probabilistic, exposes per-signal contributions and uncapped weight sum, and reports the planning threshold and expiry policy. It contains no raw extraction text or credentials. Customer context (held cards/preferences) stays separate from current intent. Suppressed preferences are removed before the intent is returned.

Expiry is the earliest selected signal's TTL or the exclusive end of the supplied end_date in UTC. SIGNAL_TTL_DAYS_JSON optionally overrides the existing default TTL by signal type. Expiry at the current clock is rejected. This is a documented date-level policy; resolving natural relative dates in destination timezones belongs to the SearchPlan phase.

## Review-only entity extraction

Request example:

```json
{
  "customer_id": "cust-dining",
  "consent": {"allowed": true},
  "text": "Destination: Paris; activity: dining; 2026-10-10 to 2026-10-15."
}
```

Both current profile consent and request consent are required, including a second profile check after an async model call. No profile, held cards, ID or signal history is sent to the model; only the submitted text is used. No new live model calls were made during Phase 4 tests.

The bounded parser supports explicit `Destination:` and `activity:` labels, a small list of city mentions and activity keywords, and exactly two ISO dates in source order. Arbitrary relative dates, multiple unlabelled locations/activities and unsupported text request clarification. It is deliberately a limited draft extractor, not general natural-language understanding or a geocoder. The returned context is accompanied by exact input quotes, missing fields and requires_confirmation=true. It never establishes confidence, eligibility or booking status, and it never writes a signal. The caller must review and submit a separate structured signal.

INTENT_EXTRACTION_MODE selects deterministic (default), mock or llm. Mock mode runs the operation through the same application LLMGateway using an explicit deterministic handler and makes no external requests. LLM mode routes `intent.entity_extraction` through the configured lightweight chat adapter by default (LLM_ENDPOINT/MODEL/API_KEY), with normal LLM_ROUTES_JSON overrides available. The model can return source quotes only. Application validation rechecks literal support, date order and deterministic ambiguity rules; the model cannot enlarge the accepted fact set. Failure or unsupported output returns a labeled deterministic draft. All classification, stage, consent and confidence rules remain deterministic.

## Compatibility and verification

The old companion recommendation workflow remains Rome travel-only. It abstains on a non-travel intent rather than silently treating it as travel; no dining/event recommendation generator is advertised by Phase 4. Existing business, merchant, outing and embedding flows are preserved.

Tests cover classification, matching booking types, duplicate/colliding IDs, confidence caps, TTL boundaries, configuration validation, mixed destinations, ownership, suppressed preferences, consent withdrawal (including during extraction), ambiguous drafts, invalid model output and gateway mock mode. The Postman Phase 4 Intent folder covers normalization, detection/debug, extraction, clarification, missing consent and unknown signals. Its synthetic event shares the existing demo trip window so collection reruns do not introduce conflicting travel dates.

Phase 5 SearchPlan generation and later hybrid retrieval remain outside this change.

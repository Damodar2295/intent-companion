# Phase 5: Search requirements

`POST /api/v1/search/plan` turns consented text and optional explicit constraints into a typed planning requirement. It does not discover places, run retrieval/routing, check eligibility, calculate savings, persist the plan or change the existing outing endpoint. Phase 6 orchestration is not included.

```json
{
  "customer_id": "cust-dining",
  "consent": {"allowed": true},
  "text": "Plan dining and shopping in Rome tomorrow at 6pm for three hours under EUR 100 with Amex offers",
  "timezone": "Europe/Rome"
}
```

The response is `READY` with `search_plan`, or `CLARIFICATION_REQUIRED` with `clarification_fields` and no plan. A ready outing contains the existing validated outing `SearchPlan` under `search_plan.outing`. The envelope also carries task, categories, current allowed preferences, origin reference, quoted input evidence, assumptions and downstream discovery/routing/value requirements. Input evidence proves what the customer requested; it is **not** verified evidence about real places. “Dining Amex benefits” produces `BENEFIT_LOOKUP` without a location, schedule or routing requirement.

Request fields include optional city, ISO date, IANA timezone, local start/end times, duration_minutes, budget, currency, travel_mode, user_location, number_of_people, include_amex_value and intent_id. Text and explicit form fields must agree. An owned, active intent can supply destination and constrain the date window; multi-day intent dates do not silently select a day. Current profile preferences are filtered against removed preferences. Neither profile/card identifiers nor separately supplied precise coordinates are sent to the model. Free text itself is sent in LLM mode, so callers should avoid putting unnecessary personal details in it.

## Validation and bounded language support

The gateway validates the strict structured interpretation schema. The application then checks quotes against the input, independently checks recognized constraints, decodes times/durations/money deterministically, and reuses destination normalization and outing timezone/DST validation. Model output cannot add eligibility, money savings, provider facts or locations. Conflicting constraints, absent categories, invalid dates, ambiguous DST times and unsupported date formats require clarification. Unknown destination timezones must be supplied explicitly; there is no geocoding in this phase.

Relative dates `today`, `tonight` and `tomorrow` use the supplied destination timezone and the injectable clock (the actual clock in realtime). Outings require destination, date, timezone, start and end/duration. Same-day windows only; crossing midnight requires clarification. No hotel origin is guessed. “Near my hotel” or “near me” requires supplied coordinates. Without a requested origin, later routing can work between stops. Walking is an explicitly labeled default. If no budget/currency is supplied, EUR is a labeled display default, not a monetary conversion. Group size defaults to one and remains editable.

The offline parser is intentionally bounded: supported category words, ISO/relative dates, 24-hour or am/pm times, numeric or one-to-six hour/minute durations, EUR/USD/GBP budget phrases, and walk/drive/transit. Its named destination vocabulary covers Rome/Roma/FCO, Paris, Milan/Milano and New York; other destinations can be supplied as `city` or `destination: City;` in text. The LLM can extract other explicitly located destinations, but deterministic constraint decoders remain bounded. Negation/ambiguity detected by the parser or model produces clarification. This is not a claim of complete natural-language understanding; arbitrary unsupported wording should be restated using the explicit form fields. No semantic embedding retrieval is invoked in this phase.

Consent is checked before and after model execution. A changed preference context returns 409; withdrawn consent returns 403. Invalid JSON/schema requests return 422, unknown customer/intent 404, and model configuration, schema or timeout failures 503. Errors do not contain provider bodies. Cancellation propagates. Responses are covered by the existing no-store middleware; plans and coordinates are not persisted. The gateway records safe operation timing and token usage, without request bodies.

## Configuration

- `SEARCH_PLAN_MODE=auto` (default): explicit mock planning in demo; LLM planning in realtime.
- `SEARCH_PLAN_MODE=mock`: offline quote extraction; no network. Invalid in realtime.
- `SEARCH_PLAN_MODE=llm`: configured shared gateway; requires a complete route, no synthetic fallback.
- `SEARCH_PLAN_TIMEOUT_SECONDS=15`: total model deadline, greater than zero and at most 30 seconds.

The new `search.requirements_generation` operation uses the lightweight logical model class and existing Responses adapter (`OPENAI_API_KEY`, explicit `OPENAI_MODEL`) at application composition. It is separate from `search.plan_generation`, preserving that operation's existing outing interpretation schema. `LLM_ROUTES_JSON` can select an existing configured adapter/model. A route contradicting mock/LLM mode is rejected; unavailable enterprise adapters never fall back. Global mock mode cannot be combined with explicit LLM search mode or realtime. Existing consumers retain their current model routes.

## Verification

`tests/test_search_plan.py` exercises requirements, benefit-only requests, contradictory fields, timezone day boundaries, ambiguous DST, hotel-origin clarification, intent ownership, removed preferences, concurrent consent changes, cancellation, model errors, timeouts and the Responses wire contract with HTTPX mock transport. Postman examples run against an isolated seeded database through `tests/test_postman.py`. No credential-enabled model request was run as part of this phase; live model quality and broader language evaluation remain unverified.

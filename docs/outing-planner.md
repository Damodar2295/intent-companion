# Phase 13: outing planner

Phase 13 exposes the existing validated outing pipeline as `POST /api/v1/outings/plan`, while retaining the streaming `/outings/stream` experience. The JSON route consumes `OutingRequest` and returns the completed `OutingPlan`.

The pipeline interprets the request, discovers configured events/places/web records, verifies field-level evidence and freshness, keeps event/venue/ticket identities separate, resolves trusted merchant branches, enriches the selected held card with synthetic illustrative matches, checks opening hours, evaluates route feasibility when an explicit origin and routing provider are available, and schedules up to three alternatives with at most four stops each. Event times, destination timezone, visit assumptions, travel mode, budget and same-day limits are validated by typed models and deterministic scheduling.

Unknown hours, advertised-minimum prices, missing event end times and route failures produce incomplete feasibility or partial results; they do not become confirmed claims. Unverified entities are excluded from schedules. The planner never invents a hotel origin, route duration, opening status or AMEX entitlement. Existing conservative aggregation keeps currencies and points separate. Prospects receive hypothetical value only; members must select a held card.

The endpoint checks customer consent and consumer segment and stores only the existing short-lived outing result policy. It does not add editable-stop operations, which belong to Phase 14. Demo output remains visibly synthetic and realtime mode never substitutes it. Provider calls use existing bounded transport, retries and freshness restrictions.

No live provider calls were made for this phase. Tests use the deterministic demo and injected provider fixtures.

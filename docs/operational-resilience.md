# Phase 18: operational resilience

Outing streams are bounded by `OUTING_DEADLINE_SECONDS` (one to 120 seconds), cancel child provider work when the client disconnects, and release the per-customer active-run slot in a `finally` block. Completed work is retained only when the pipeline reaches its terminal event; an interrupted stream is not presented as a completed itinerary.

Deadline expiry produces a partial result with an explicit warning. Provider failures remain isolated to their stage, while consent or preference changes invalidate the run and remove its customer-visible plan. The short-lived store continues to purge expired plans and never persists precise origin coordinates or provider payloads.

# Phase 14: editable outings

`POST /api/v1/outings/{id}/edit` applies bounded mutations to a short-lived stored `OutingPlan`. The customer and consent context are rechecked through the existing run store. Supported operations are `REMOVE_STOP`, `CHANGE_CATEGORY`, `CHANGE_BUDGET` and `CHANGE_DURATION`.

Edits preserve the destination, date, timezone, transport mode, origin policy, card selection, evidence and unaffected constraints. The response is marked `PARTIAL` with a fixed revalidation warning because changing stops, budget or duration can invalidate routes, opening hours, event timing and value totals. Removed stops are removed from alternatives; category changes retain only matching stops; budget changes update the plan constraint without inventing eligibility; duration changes update assumed non-event visit durations. Existing event schedules are never overwritten.

`ADD_STOP` and `REPLACE_STOP` intentionally return 422. A new place must pass the full discovery, identity, freshness and scheduling pipeline; accepting arbitrary client JSON would invent an unverified stop. A fresh Phase 13 plan is required for those changes. No database persistence or long-lived edit history is added. Expired runs, withdrawn consent and changed preferences are rejected by the existing short-lived store policy.

This phase does not generate prose, recalculate merchant value, call the LLM, or silently recompute route estimates. Phase 15 grounded response generation remains separate.

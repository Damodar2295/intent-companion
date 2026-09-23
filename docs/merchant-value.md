# Phase 12: merchant resolution and AMEX value

Phase 12 adds `POST /api/v1/value/preview` over the existing deterministic outing value services. It resolves a real-world entity against configured branch mappings, then evaluates the existing synthetic catalog for a selected held card and date. Every match is labeled **Demo / illustrative AMEX value**.

Merchant identity requires an exact trusted place identifier or corroborating branch evidence (normalized name plus exact address plus exact website). Name similarity alone cannot attach a merchant. Synthetic fixture IDs are accepted only for synthetic entities. Events never become merchants: event, venue and ticket seller identities remain separate. No match produces no direct merchant-specific value.

Catalog matches respect selected card, validity dates, refresh expiry and confirmed condition IDs. Unfulfilled conditions remain in the match but `eligible` stays false. Existing conservative aggregation keeps cash currencies separate, points separate from cash and one selected value per explicit stacking group. This endpoint does not convert currencies, claim live inventory, calculate a customer’s final benefit eligibility or make savings promises.

Member requests must select a held card; prospects can use a hypothetical product comparison but no entitlement is implied. Consent is required. The endpoint does not persist entities or provider payloads. Realtime discovery, verification and routing remain the preceding provider stages; itinerary scheduling is Phase 13.

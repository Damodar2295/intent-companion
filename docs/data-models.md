# Domain and persistence

All public models reject undeclared fields. Synthetic markers must be true. Preference tags are restricted to the six explicitly supported non-sensitive interests. This minimizes data but is not a production PII classifier: operators must not submit real data into free-text source/origin fields.

| Object | Key semantics |
| --- | --- |
| IntentSignal | Unique event ID, customer ID, source, normalized event type, timezone-aware timestamp, consent and structured context. Consent defaults to denied. |
| CustomerContext | Lifecycle, held product IDs, market, segment, stated preferences, explicit suppression list and current consent. |
| IntentContext | Separate trip destination/dates/purpose, stage, active preferences, confidence, contributing signal IDs/evidence, creation and expiry. |
| CardProduct | Product identity, mock description/categories, contextual-only product rule, source/version, freshness and validity. No underwriting attributes. |
| Benefit | Parent product, category, explicit applicability rule, conditions, savings or experiential type, optional amount/currency. |
| Offer | Merchant reference, eligible product IDs, date/location checks, conditions and optional fixed mock saving. |
| MembershipRewardOpportunity | Parent product, explicit fixed mock points rule and decimal mock conversion rate. Not a live earning rate. |
| Merchant | Fictional Rome place with explicit accepting product IDs and verification metadata. |
| Recommendation | Approved catalog description, applicable product IDs, relevance, evidence, source IDs, conditions and per-product calculated values. |
| CompanionExperience | Intent, grouped recommendations, per-card currency-separated totals, explanations, preferences used, provider mode, trace, status and abstention reasons. |

Catalog records use `item_id` plus their domain-specific IDs, `kind`, `source`, `catalog_version`, `last_verified`, `valid_from` and `valid_to`. The common validity interval is the Benefit validity representation. Base catalog fields make all item types equally subject to freshness and validity checks.

Evidence has a stable ID, type, source ID, factual statement and optional signal weight. An intent stores the signal evidence; each recommendation adds intent, preference, catalog and deterministic rule evidence at selection time. Merchant offers also reference the merchant and applicable card sources.

## Confidence and ranking

Default signal contributions: booking `.90`; declared intent `.90`; travel search `.45`; hotel search `.40`; restaurant booking `.30`; restaurant search `.15`; event search `.15`; ad click `.10`; website/app interaction `.10`. Confidence is `min(1, sum(unique signal-type weights))`, not a probability. Repeated IDs are idempotent at ingestion; changed content under the same ID is a conflict. Repeated types contribute zero additional confidence. Aliases: flight_search → travel_search, restaurant_reservation → restaurant_booking, declared_intent → customer_declared_intent. Rome, Roma and FCO normalize to Rome.

Signal TTL is 30 days. Intent expiry is the earliest contributing signal expiry or midnight UTC following the trip end. A travel booking makes the intent booked; otherwise a score ≥ .4 makes it planning, and lower scores exploring. Signals selected for different trips are rejected together; explicit signal IDs select a trip. The engine conservatively abstains if any selected signal is unpermissioned or invalid instead of silently discarding it.

Default relevance is `min(1, .2 + .3 × matching active preference tags)`. Stable ID ordering breaks ties. Non-card items with preference tags require an active tag match; untagged travel items can match the Rome context alone. Held-card comparisons retain valid alternatives, even when their relevance is lower. Removal suppresses the exact preference tag, not a semantic inference about related tags.

## Value rules

All monetary arithmetic uses Decimal and rounds to two decimal places with ROUND_HALF_UP. Fixed catalog savings use `mock_catalog_fixed_amount`; reward value is points × explicit mock rate. Experiential items are not monetized. A claimed monetary item with missing amount/rate/currency is excluded from recommendation results.

`stackable=true` plus a nonempty `stacking_group` explicitly authorizes combination across groups. Within each product/currency/group only the greatest value counts; ties resolve by deterministic retrieval order. Unknown stacking is excluded from totals. No currency conversion or aggregation across currencies/cards occurs. Every excluded alternative remains visible with a reason. Prospect values assume a hypothetical product and qualifying mock purchase, not an entitlement or approval.

## Storage

SQLite tables: metadata (seed version), customers, signals (indexed by customer), intents, catalog (indexed by market/segment/geography/kind), experiences (audit snapshots). Catalog queries use bound SQL parameters. Product references are checked in the matching service after indexed candidate retrieval. The seed flag is written transactionally with data; subsequent startup does not overwrite mutable profiles. Schema/catalog migration is deliberately not automatic beyond initial v1 creation.

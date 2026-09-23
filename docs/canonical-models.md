# Phase 2 — canonical domain models

The canonical import surface is `agent.canonical`. It reuses existing models rather than introducing parallel consumer or outing schemas. Old imports and existing serialized field names remain supported.

| Canonical model | Implementation | Validation / compatibility |
|---|---|---|
| CardProduct, Benefit, Offer, Merchant | agent/domain.py | Discriminated catalog kind, validity order, finite/nonnegative monetary fields, currency format |
| RewardOpportunity | Alias of MembershipRewardOpportunity | Existing points and Decimal fields; no new point-to-cash conversion |
| CustomerContext, IntentSignal | agent/domain.py | Existing consent, lifecycle, normalized signal types and timezone-aware signal timestamps |
| IntentContext | agent/domain.py | Date order, aware timestamps, positive lifetime, bounded confidence |
| Recommendation, Evidence | agent/domain.py | Recommendations require evidence and source references; nonempty evidence identifiers/facts, bounded optional weights |
| SearchPlan, OutingRequest | agent/outing/models.py | Existing destination timezone/DST/time-window checks, positive budget, currency format |
| OutingPlan, Route | agent/outing/models.py | Aware timestamps and positive freshness windows; nonnegative route measurements; Route aliases RouteLeg |
| Source | agent/canonical/models.py | Explicit source classification, freshness window, attribution, completeness; discovery is not verification |
| Place, Event | agent/canonical/models.py | Separate identities; event venue reference, aware ordered schedule, matching destination offset, optional paired price/currency |
| AmexExperience | agent/canonical/models.py | Product applicability, conditions, validity window, explicit relationship evidence |

All models reject extra fields and nonfinite numeric values. Existing synthetic consumer/catalog records now expose `source_type: SYNTHETIC` alongside the existing `synthetic: true`. Older stored JSON remains readable through defaults. No migration or reseeding is required, and existing user preferences are preserved.

Legacy catalog records with missing sources or currencies remain readable: existing deterministic matching excludes them. The seed validator rejects these incomplete records before ingestion. Schema validity does not establish truth, eligibility, freshness at request time, source authority or satisfied offer conditions; existing domain validators retain those responsibilities. FieldEvidence's existing `DEMO` provider category remains unchanged for compatibility.

## Seed data and validation

Existing catalogs, customers and signals keep their identities and quantities, with explicit synthetic source labels. `data/knowledge.json` adds one synthetic source, three same-name fictional venues across Rome/Milan/Paris, six recurring events on distinct dates and three illustrative AMEX experiences. Prices, ticket availability and opening hours are unknown rather than invented. Event identities remain distinct across dates and venues. Experience-to-event links have explicit evidence; sharing a venue does not confer eligibility.

Run from the application root:

```sh
.venv/bin/python -m scripts.validate_seeds
.venv/bin/pytest tests/test_canonical.py -q
```

The read-only seed validator checks all consumer catalog files and the new knowledge bundle, including duplicate IDs, source/venue/evidence references, geography consistency, product applicability and customer/signal references. It reports counts and exits unsuccessfully on invalid data.

The new knowledge bundle is seed input only. It is not served as live event inventory, is not read on customer requests, and does not activate the unavailable AMEX-experience provider. This phase establishes a small canonical fixture set; the larger configurable retrieval corpus and ingestion/indexing belong to subsequent work. The existing SQLite runtime source remains unchanged.

## Boundaries

No new endpoint, frontend, provider invocation, vector store, embeddings, ingestion pipeline or hybrid search is introduced. Existing Postman requests remain applicable and their replay tests exercise the additive response fields. Source URL validation is syntactic provenance validation, not permission to fetch a URL; restricted retrieval retains its separate SSRF protections. SafeChain and all live-provider credentials remain outside this phase's validation.

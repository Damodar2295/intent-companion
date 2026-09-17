# Verification and known limitations

## Verified locally

- Backend: **67 tests passed** in the project's isolated Python 3.12 environment.
- Frontend: **6 tests passed** (scenario switching, preference removal, consent withdrawal/restoration, evidence, initial API failure, excluded-value display).
- Ruff backend lint passes; TypeScript compilation, ESLint and Vite production build pass.
- Browser walkthrough with the real local API verified all three journeys, distinct leading cards, shopping removal (USD 135 → USD 90), consent abstention/restoration and local-only prospect application messaging. No browser console errors or warnings were observed in that walkthrough.
- Responsive DOM geometry at 390px and 320px showed no horizontal overflow; narrow-screen content was inspected. Viewport override was reset after testing.
- Server readiness, static UI and OpenAPI documentation are available locally.

Backend tests cover aliases/date normalization, timezone requirements, configurable confidence weights and repeat caps, event idempotency/conflicts, profile/signal consent, expiration, incompatible trips, unknown IDs, ownership, protected/undeclared-field rejection, persistence across restart, scenario differences, held-card constraints, source resolution, catalog freshness/validity/dependencies, missing value inputs, currency separation, unknown stacking, decimal rewards, experiential non-valuation, no matches and error redaction. AI tests cover valid constrained reorder, absent config, HTTP failure, timeout, invalid JSON, invented candidate IDs, unsupported prose, invalid evidence, duplicate/missing candidates, and preferences/consent changing during an in-flight model request.

## Not claimed

- No live LLM invocation: no credentials were copied or used. The optional compatible chat-completions adapter needs a configured endpoint/model/key and is verified with a mocked HTTP transport only. Its wire format follows the [official chat-completions reference](https://developers.openai.com/api/reference/cli/resources/chat/subresources/completions). The adapter permits ordering and evidence identifiers, not factual prose.
- No deployment, production authentication, underwriting, payment, booking, real merchant acceptance or actual benefit verification.
- No automated cross-browser visual regression suite; browser validation was a local walkthrough.

## Limitations

- Single-user localhost prototype. Customer IDs are not authentication. Do not expose it publicly or enter real data.
- One destination, six explicit preference tags, fixed trip fixtures and a bounded mock rule vocabulary. Preference suppression is exact-tag based, not semantic. Arbitrary text/entity extraction is intentionally not used.
- All selected signals must be valid and describe one compatible trip; invalid mixed bundles abstain rather than silently dropping inputs. A caller selects signal IDs to isolate a trip.
- Catalog retrieval is SQL-filtered by market/segment/geography; dependent applicability rules run in Python over the small result set.
- Monetary descriptions in the curated fixtures and their structured amounts must be maintained together. The system does not independently fact-check arbitrary catalog prose; the catalog is the trusted source boundary.
- Audit snapshots retain synthetic historical evidence after preference removal; removed tags no longer affect future recommendations. There is no audit-retention/deletion admin UI.
- SQLite schema/catalog upgrades beyond seed v1 require an explicit migration. Changing seed JSON does not silently overwrite an existing database.
- Card fees, actual spending, currency conversion, production offer enrollment, live availability and multi-card spend optimization are not modeled.
- Test execution reports a third-party Starlette/AnyIO deprecation warning; all assertions pass.

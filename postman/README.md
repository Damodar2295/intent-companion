# Existing API collection

Import IntentCompanion.postman_collection.json and IntentCompanion.postman_environment.json into Postman. Select the environment and set baseUrl to your localhost backend (the example uses port 8092). No credentials are included. Customer and business identifiers refer to synthetic seeded fixtures.

Run against a disposable database: these requests ingest synthetic signals and modify preferences and consent. The collection restores its consent/preference examples, but it is not a transaction and an interrupted run can leave changes. Never point it at a customer database.

From the application root, one isolated demo startup example is:

```sh
DATABASE_PATH="$(mktemp -d)/postman.sqlite3" DEMO_MODE=true REALTIME_MODE=false AI_PROVIDER=deterministic .venv/bin/uvicorn agent.main:app --host 127.0.0.1 --port 8092
```

Run folders in collection order. Returned consumer/business intent IDs and the outing ID are captured in environment variables. Requests cover health, scenario listing, signal ingestion, detection, companion generation, preferences, consent, feedback, business goals, merchant resolution, outing capabilities, planning/retrieval and expected failures. There are no future `/api/v1` routes. Trip dates/location and synthetic profile IDs are editable environment variables. modelMode documents the example mode; changing it does not configure the backend.

The outing POST uses JSON input and an SSE response. Its script parses the completed stream, verifies a result and captures outingId. Postman may buffer events until the request finishes; use the application UI to inspect incremental progress and cancellation. Do not parse SSE as ordinary response JSON.

Automated validation:

```sh
.venv/bin/pytest tests/test_postman.py -q
```

This uses FastAPI TestClient with a freshly seeded in-memory database, checks route coverage, and executes the collection's JavaScript test scripts with Node. Node must be installed (the frontend already requires it). Tests use demo providers and require no external credentials. This is not a live-provider smoke test or a claim that Postman's desktop runner was exercised.

Phase 3 adds **Infrastructure → Persistent retrieval index statistics**, a read-only check of `/api/infrastructure/index`. Run the [ingestion CLI](../docs/vector-ingestion.md) first and point the application at that same SQLite index to see populated counts. The collection also passes against an empty index; it does not generate embeddings. The endpoint explicitly reports that semantic quality is unverified and customer retrieval is not enabled.

Phase 4 adds **Phase 4 Intent** requests for the implemented `/api/v1/intent/signals`, `/detect` and `/extract` endpoints. Run with the default deterministic extraction mode for reproducible assertions, or INTENT_EXTRACTION_MODE=mock to exercise the shared gateway without network calls. The folder captures phase4IntentId and checks classified event intent, explained confidence, draft evidence, clarification, missing consent and unknown signal ownership. These are the only versioned endpoints currently included.

The **Phase 5 — Search planning** folder covers a dining/shopping outing, benefits-only lookup, missing hotel-origin clarification and denied consent at `/api/v1/search/plan`. Run the default demo configuration for deterministic assertions. These are ordinary JSON responses, not SSE, and do not call discovery/routing or assert AMEX eligibility. Live mode requires a configured LLM route and may request additional clarification.

The **Phase 6 — Tool orchestration** folder exercises `/api/v1/search/execute` in default demo mode: dining discovery, Rome catalog-only retrieval, partial event discovery with unavailable demo web, clarification before tools, denied consent and invalid input. Assertions inspect selected tool traces and output usage labels. These responses are ordinary JSON, not SSE or final itineraries. Realtime tests require provider configuration and are separate from deterministic collection replay.

The Phase 7 retrieval examples query `/api/v1/retrieval/search` with synthetic consented data and inspect RRF/debug fields. Retrieval hits are candidates only; no eligibility, savings or recommendation claim is made.

Phase 8 ranking diagnostics are returned by the retrieval endpoint when `RERANKER_MODE=test_hash` is explicitly enabled. Default collection replay leaves reranking disabled and verifies the endpoint remains a candidate-only retrieval surface.

Phase 10 includes a read-only `/api/v1/llm/routes` request that validates operation coverage and confirms route diagnostics do not expose keys or endpoints.

Phase 11 includes `/api/v1/providers/capabilities`, validating provider roles, freshness metadata and the absence of secrets. It does not make live provider requests.

Phase 12 includes `/api/v1/value/preview` with a verified synthetic Rome entity and held card. Assertions check the illustrative label and separate-currency/points flags. It does not claim live offers or eligibility.

Phase 13 includes `/api/v1/outings/plan` with the seeded Rome dining/culture/event scenario. Assertions verify alternatives, evidence and bounded stop counts; this is a plan projection, not an editable outing.

Phase 14 edit requests are covered by tests; the importable collection keeps the default plan surface focused on Phase 13 because edit IDs are generated at runtime. New stop operations intentionally return 422 until a fresh verified plan is created.

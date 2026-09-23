# Intent Companion

A working, evidence-backed Rome travel demo: **Detect → Understand → Activate**. A FastAPI / LangGraph modular monolith, SQLite repositories, and a blue-and-white React / TypeScript interface. All people, products, merchants, offers and values are synthetic. This is not a chatbot, credit assessment, booking service, or a representation of real card benefits.

## Run locally

Requirements: Python **3.11+** (tested with 3.12), Node **20.19+ or 22.12+**, npm. No model credentials or database service needed.

```sh
# From this directory; use python3.12 if your python3 is older than 3.11.
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
cd frontend
npm ci
npm run build
cd ..
bash scripts/start_local.sh
```

Alternatively, with uv: `uv venv --python 3.12 .venv` followed by `uv pip install --python .venv/bin/python -e '.[test]'`.

Open [the demo](http://127.0.0.1:8090/app/) or [interactive API documentation](http://127.0.0.1:8090/docs). The startup script binds only to localhost. Build the frontend before starting the server, or restart after the first build. For UI development, run `npm run dev` inside frontend; Vite serves `/app/` on port 5174 and proxies `/api` to port 8090.

SQLite is created and seeded automatically at `var/companion.sqlite3`. Preferences persist across restarts. Use **Restore scenario preferences** in the UI to reset a profile's preferences; it does not override consent. For a separate fresh demo database, set `DATABASE_PATH` to a new local filename. No destructive reset is necessary.

## What to try

1. **A taste of culture:** held-card comparison favors Savor for fine dining and museums; USD 60 synthetic potential value.
2. **A considered escape:** the same held cards favor Sanctuary for shopping and luxury hotels; USD 135 synthetic potential value.
3. Remove **shopping** from the second member journey: its potential value changes to USD 90 and shopping recommendations disappear.
4. Turn off **Allow personalization**: recommendations clear and the application abstains.
5. **Prospect:** switch to the Prospect journey to compare fictional products with local mock exploration/application actions only. Direct links: [Prospect](http://127.0.0.1:8090/app/?journey=prospect) and [Card Member](http://127.0.0.1:8090/app/?journey=member).
6. Expand **Why you’re seeing this**, **See the calculation**, and **Inspect signals & confidence** to audit each decision.

These amounts are scenario illustrations, not actual savings, and do not combine alternative cards. Fees are not modeled.

## Configuration

Optional `.env` file is loaded without overriding existing process environment. `.env.example` contains placeholders only.

| Variable | Default / behavior |
| --- | --- |
| `PORT` | Shell startup override, default `8090`; use `PORT=8091 bash scripts/start_local.sh`. |
| `DATABASE_PATH` | Project-local `var/companion.sqlite3`. Relative overrides resolve from the process working directory. |
| `DEMO_MODE` | `true`: fixed clock at `2026-09-17T12:00:00Z`. `false`: real UTC clock; old fixture trips/signals safely expire. |
| `AI_PROVIDER` | `deterministic`; set `llm` to explicitly enable optional external ranking. |
| `LLM_ENDPOINT` | Full chat-completions endpoint; empty by default. HTTPS required except localhost. |
| `LLM_MODEL` | Explicit provider model ID; no default or claim of model availability. |
| `LLM_API_KEY` | Empty by default; never commit credentials. |
| `LLM_TIMEOUT_SECONDS` | `8`; maximum `30`. Invalid/unavailable responses fall back. |
| `INTENT_WEIGHTS_JSON` | JSON overrides of the documented signal weights, each between 0 and 1. |

The optional adapter sends only filtered candidate identifiers, categories, scores, permitted preference tags and allowed evidence identifiers. No customer IDs, raw signals, amounts or dates are sent. External ranking is opt-in. Network access is not needed for default runtime after dependencies are installed. No live LLM call was made during verification.

## Structure

```text
agent/
  main.py                API and request/error boundary
  initialize.py          lifespan and dependency initialization
  factory.py, graph.py   bounded workflow construction
  domain.py              Pydantic contracts
  repositories.py        repository protocol and SQLite persistence
  customer_context.py    preference edits and historical suppression
  intent_engine.py       consent, normalization, confidence and expiry
  matching.py            structured retrieval and applicability rules
  value_calculation.py   Decimal calculations and conservative aggregation
  ai.py                  deterministic / guarded LLM ranking adapters
  orchestration.py       evidence-preserving experience composition
config/                  environment settings and clock
data/                    versioned synthetic JSON fixtures
frontend/                React / TypeScript demo and UI tests
tests/                   backend unit, integration and safety tests
docs/                    architecture, API, model, demo and verification notes
```

The copied starter's unrelated CRM, vector retrieval and enterprise deployment code was removed; API, initialization, factory and LangGraph boundaries were retained. The original reference application was not modified.

## Verify

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check agent config tests
.venv/bin/ruff format --check agent config tests
cd frontend
npm test
npm run lint
npm run build
npx prettier --check src index.html package.json
```

See [architecture](docs/architecture.md), [data models](docs/data-models.md), [API examples](docs/api.md), [demo walkthrough](docs/demo.md), and [verification and limitations](docs/verification.md).

## Live outing discovery

The consumer journey now includes an outing planner for dining, shopping, culture and events. It defaults to explicitly fictional offline demonstration, with separate realtime adapters for OpenAI Responses, Brave, Google Places, Google Routes and Ticketmaster. AMEX enrichment remains **Demo / illustrative AMEX value** in both modes. Existing recommendation and business journeys remain available.

See [the outing operating guide](docs/outing.md) for setup, API examples, evidence and storage policies, validation, and the credential-enabled smoke test. Realtime interpretation requires `OPENAI_API_KEY` and an explicit `OPENAI_MODEL`; other missing providers yield partial results. No live API calls are made by the default configuration.

### Phase 1 provider boundaries

Model invocations now share an injected gateway while existing consumer, business and outing APIs remain compatible. See [provider configuration and SafeChain contract](docs/provider-boundaries.md) and the [Postman collection instructions](postman/README.md). Retrieval interfaces are preparatory only; no semantic search or enterprise integration is claimed. Phase 2 is not implemented.

### Phase 2 canonical schemas

[Canonical model documentation](docs/canonical-models.md) describes the shared import surface, additional provenance/event/experience schemas and synthetic fixtures. Validate seed integrity without changing the database using `.venv/bin/python -m scripts.validate_seeds`. Vector ingestion remains outside this phase.

### Phase 3 ingestion

[Vector ingestion instructions](docs/vector-ingestion.md) cover the persistent SQLite vector/FTS index, versioned upserts and `GET /api/infrastructure/index`. Embeddings are disabled by default. Explicit openai mode generates real embeddings using OPENAI_API_KEY and EMBEDDING_MODEL. test_hash remains a non-semantic test option; no enterprise embedding integration is claimed. Customer retrieval remains unchanged.

### Phase 4 intent engine

[Intent service documentation](docs/intent-service.md) covers the versioned signal/detection APIs, travel and lifestyle classification, transparent confidence, expiry and consent safeguards. Entity extraction is review-only, with deterministic, mock and optional gateway-backed modes. SearchPlan generation remains the next phase.

Phase 5 adds [validated search requirements](docs/search-plan.md) at `POST /api/v1/search/plan`, with explicit mock/LLM modes, clarification responses and Postman examples. It stops before Phase 6 discovery orchestration.

Phase 6 adds [bounded tool orchestration](docs/tool-orchestration.md) at `/api/v1/search/execute`, with concurrent selected providers, deadlines, safe invocation traces and partial results. This is a discovery/catalog stage, not a final itinerary; Phase 7 hybrid retrieval is not included.

Phase 7 adds [hybrid retrieval](docs/hybrid-retrieval.md) at `/api/v1/retrieval/search`, combining filtered lexical and configured semantic candidates with RRF diagnostics. It stops before reranking and business acceptance.

Phase 8 adds optional [reranking and threshold diagnostics](docs/reranking.md) to retrieval. It preserves channel/RRF scores and does not perform eligibility or savings validation.

Phase 9 adds [bounded context construction](docs/context-engineering.md) at `/api/v1/context/build`, with evidence selection, deterministic pruning and token diagnostics.

Phase 10 adds [safe model-route diagnostics](docs/model-routing.md) at `/api/v1/llm/routes` while keeping all model calls behind the shared gateway.

Phase 11 documents [provider integrations](docs/provider-integrations.md) and adds safe capability reporting at `/api/v1/providers/capabilities`.

Phase 12 adds [deterministic merchant/value preview](docs/merchant-value.md) at `/api/v1/value/preview`, with explicit illustrative AMEX labels and no invented entitlement.

Phase 13 adds the JSON [outing planner](docs/outing-planner.md) at `/api/v1/outings/plan`, reusing verified providers, routing feasibility and conservative schedule/value validation.

Phase 14 adds [bounded editable outings](docs/editable-outing.md) for removing stops and changing constraints while rejecting unverifiable new stops.

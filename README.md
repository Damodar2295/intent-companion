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

#prompt
Create an 8-second cinematic product-concept advertisement, 16:9 widescreen.

CHARACTER AND STYLE:
Natasha is an American woman in her early thirties, with shoulder-length dark brown hair, wearing a cream blazer over a navy top. Maintain realistic facial features and hands. Premium travel-advertising aesthetic: warm natural light, elegant blue-and-white mobile interface, minimal text, smooth camera movement.

STORY:
0–2 seconds:
Over-the-shoulder shot of Natasha at home, excitedly viewing an October flight-booking confirmation on her smartphone. A silver American Express Platinum card rests beside her passport on the table. Do not show readable card numbers, passport details, or invented flight information.

2–4 seconds:
Close-up of her phone. She opens a proposed travel assistant and taps “Use this trip,” explicitly choosing to share her booking. Show a simple trip card reading “October getaway.” Transition through a graceful match-cut to Natasha arriving outside her destination hotel in the same outfit.

4–6 seconds:
Natasha taps “Use my location.” The app displays a clean local map centered on her hotel. Three distinct icons appear: a nearby restaurant, a shopping boutique, and an evening music venue. A dotted walking route connects them.

6–8 seconds:
The map slides into an elegant itinerary headed “Your evening, planned.” Three image cards show dining, shopping, and nightlife. A small section reads “Explore eligible card offers.” End on a steady close-up of Natasha holding this itinerary on her phone; this is the continuity frame for the next clip.

VOICEOVER:
“October getaway booked. What if Natasha’s Platinum membership helped shape what comes next?”

AUDIO:
Warm female narration, subtle uplifting instrumental music, soft transition into city ambience.

IMPORTANT:
Keep a small “Concept demo” label visible throughout. Portray a proposed product, not an existing AMEX service. No specific discounts, guaranteed benefits, or confirmed reservations. Keep screen text short and legible. Avoid floating holograms, crowded screens, and rapid cuts.
Create an 8-second continuation of the previous product-concept advertisement, 16:9 widescreen. Use the previous clip’s final frame as the opening reference.

CONTINUITY:
Use exactly the same Natasha: American woman in her early thirties, shoulder-length dark brown hair, cream blazer over a navy top. Preserve the same smartphone, blue-and-white app interface, destination streets, and itinerary. Begin in late-afternoon light and progress naturally toward an evening atmosphere.

STORY:
0–2 seconds:
Begin with the same close-up of Natasha’s itinerary. She selects “Walk nearby.” The map highlights a short route from her hotel to dinner, a boutique, and an evening music venue. Each stop displays a walking icon and a concise category label.

2–4 seconds:
The dining card expands into an illustrative benefit panel:
“Eligible offer”
“Potential savings”
“Check terms”
Use a simple wallet icon and a subtle highlighted savings area, without inventing a dollar amount. Include a readable secondary label: “Illustrative — eligibility and enrollment may apply.” Natasha taps “View terms,” then returns to her itinerary.

4–6 seconds:
Two fluid cinematic shots: Natasha enjoying an inviting neighborhood restaurant, then browsing a stylish independent boutique along the walking route. Present these as imagined moments from her proposed itinerary, not proof of a redeemed benefit or completed purchase.

6–8 seconds:
Natasha approaches a tasteful live-music venue on a lively pedestrian street. Finish with her phone’s three-stop itinerary in the foreground and the evening city softly blurred behind it. Display the closing headline:
“Your trip. Your benefits. More possibilities.”

VOICEOVER:
“Nearby dining, shopping, and nightlife—with relevant offers and potential savings, clearly explained.”

AUDIO:
Continue the first clip’s music seamlessly. Add gentle restaurant ambience and a subtle live-music finish.

IMPORTANT:
Keep “Concept demo” visible throughout. Do not imply every venue accepts a particular offer or that Platinum membership guarantees savings. No fabricated offer amounts, booking confirmations, or automatic benefit redemption. Prioritize an elegant, uncluttered story with realistic human movement.

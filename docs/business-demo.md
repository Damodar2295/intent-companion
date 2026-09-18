# Business and merchant expansion

## Run locally

Use Python 3.12 and a current Node.js runtime. From the repository:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
cd frontend
npm ci
npm run build
cd ..
bash scripts/start_local.sh
```

On Windows use `.venv\Scripts\python` and run `python -m uvicorn agent.main:app --host 127.0.0.1 --port 8090` directly. The Python lock is a tested-environment version snapshot, not a cross-platform hash lock. Frontend dependencies use package-lock.json.

Open `/app/?journey=business&scenario=bakery` or `scenario=consultancy`. Consumer links remain unchanged. The frontend uses relative `/api` URLs. Configure `PORT`, `DATABASE_PATH`, `FIXTURE_DIR`, `DEMO_NOW`, `DEMO_MODE`, and model settings as described in `.env.example`. Development proxy overrides belong in `frontend/.env.local`. Never expose this single-user application publicly.

## Seven-minute walkthrough

1. **0:00–1:00 — A business, not a chatbot.** Open Northstar Bakery. Explain the second-location goal and separate observed, planned, and potentially card-addressable spend. These are not savings.
2. **1:00–2:00 — Evidence becomes intent.** Expand the presenter disclosure. Show declared, observed and scheduled evidence, unique event-type weights, and the unconfirmed status. Confirm the intent explicitly.
3. **2:00–3:00 — Explain value.** Select Flow: packaging savings are `min(2500 × .04, 100) = $100`; ingredient reward value is `4000 × 2 × .01 = $80`. The $50 packaging reward alternative is not added. Select Grow to show equipment and employee-control opportunities. Employee features have no invented dollar value.
4. **3:00–4:00 — Merchant moment.** Expand merchant lookup. Use the three QR examples to show verified acceptance plus an offer, verified acceptance without an offer, and unknown/stale acceptance. Unknown never means rejected. No camera or payment is involved.
5. **4:00–5:00 — Customer control.** Change a spend amount or priority and rebuild through the API. Dismiss the intent and reload: recommendations stay dismissed. Restore it to continue. Consent withdrawal always overrides confirmation.
6. **5:00–6:00 — Same cards, different business.** Switch to Fieldwork Consulting. Software, travel and employee needs replace packaging and equipment. Same held cards, different context. Flow illustrates $60 software savings; Grow illustrates $90 travel reward value.
7. **6:00–7:00 — Grounded AI and consumer connection.** Prepare a free-text goal draft, review it, then apply and rebuild. Explain that extraction cannot invent amounts or eligibility. Switch to Card Member to show merchant lookup and explicit shared-spending exploration. All application actions are local demonstrations.

## Code map

- `agent/business/models.py`: strict separate business contracts and fixture validation.
- `store.py`: additive SQLite extension records and one-time fixture installation. Existing consumer tables, preferences and audit records remain intact.
- `intent.py`: goal/owner isolation, consent, freshness, repeated-type confidence, observation deduplication and evidence origins. Overlapping aggregate periods abstain.
- `matching.py`: held-card, industry, goal, category, geography, supplier acceptance and catalog freshness checks.
- `value.py`: Decimal rules, thresholds, goal-wide caps, per-card alternative selection, separate spend/savings/rewards.
- `service.py`: fixed LangGraph guard → retrieve → calculate → rank → compose; refreshes intent before delivery.
- `extraction.py`: provider-neutral draft interface; deterministic default and bounded optional LLM adapter. The UI requires review; extraction itself never persists signals.
- `agent/feedback.py`: stable owner/goal or owner/trip feedback, independent of transient intent IDs.
- `agent/merchant.py`: acceptance and offers evaluated separately.
- `frontend/src/BusinessApp.tsx`: business experience and structured input editor. `JourneyShell.tsx` and `ExperienceControls.tsx` provide shared navigation and controls.

## API examples

Both root paths and `/api` aliases are supported. Open `/docs` for request schemas.

```json
POST /business/intents/detect
{"business_id":"biz-bakery","goal_id":"goal-bakery-growth"}

POST /business/companion
{"business_id":"biz-bakery","intent_id":"<returned intent_id>"}

POST /merchant/resolve
{"owner_type":"business","owner_id":"biz-bakery","code":"DEMO-PACKAGING"}

POST /business/intents/<intent_id>/feedback
{"owner_id":"biz-bakery","action":"dismiss"}

POST /business/goals/extract
{"business_id":"biz-bakery","text":"Expand with packaging and equipment in the next 3 months"}
```

Other additions: GET `/business/scenarios`, GET `/businesses/{id}`, PUT `/businesses/{id}/preferences` (`priorities` array), PUT `/businesses/{id}/consent`, POST `/business/signals`, GET `/business/intents/{id}/signals?business_id=...`, and consumer `/intents/{id}/feedback`. Feedback actions: confirm, dismiss, restore. Unknown owned resources return 404; invalid input returns 422; insufficient evidence returns structured abstention.

## Fixture authoring and upgrades

`data/business.json` holds scenario labels/defaults, two held products, two businesses, seven suppliers (one stale), eleven opportunities (including expired and missing-rate examples), and signal sequences. Models reject extra fields, malformed records, duplicate IDs, and broken scenario/opportunity references with the fixture filename and record path.

Use stable unique business, goal, event and observation IDs. Spend records represent category-period aggregates, not arbitrary transactions. Use a new observation ID for a new nonoverlapping period; repeated copies must be identical. A recurring pattern needs multiple dated, nonoverlapping observed periods. Planned spend is not an observation of a completed transaction.

Fixtures choose named `percent_savings`, `points_per_dollar`, or `informational` code rules and explicit rates/thresholds/caps/stacking groups. Monetary fixtures use USD only. Do not place executable formulas or real product claims in JSON. New categories/rules require model and test changes.

Installation uses SQLite transactions and a `business_seed_v1` marker. Existing rows are not overwritten on restart. Edited selections, priorities, consent and feedback persist. Changing a fixture does not overwrite an installed database: use a new disposable DATABASE_PATH to preview fixture changes, or add a deliberate versioned migration for existing installations. Do not delete a user's database to upgrade.

## Verification and boundaries

83 backend tests and 11 frontend tests passed; Ruff, ESLint, TypeScript and the production build passed. Tests include both business journeys, monetary examples, duplicate replay, persistent dismissal after reopening SQLite, owner/consent checks, all three consumer/business merchant outcomes, invalid extraction fallback and explicit supplementary interest.

Live browser checks covered loaded business recommendations, bakery/consultancy content, desktop presentation and a 390px viewport with no document horizontal overflow. The complete requested viewport/state matrix and live external-model behavior are not yet certified. No external model credentials were used.

This remains a synthetic single-user demo: no underwriting, entitlement guarantee, payment scheduling, merchant onboarding, bookings, real application submission, fees model, production authentication or deployment. Free-text drafts are deliberately narrow; unsupported goals need structured input. Consumer journey decomposition and consumer simulator metadata are not fully moved into the new shared fixture architecture. Business replay currently rebuilds the selected signal set rather than offering an animated event-by-event player.

# Five-minute demo walkthrough

Start the server, open `/app/`, and leave AI_PROVIDER at deterministic. No credentials or external runtime services are required. The synthetic date is fixed at September 17, 2026 so the October 10–15 trip stays reproducible.

The customer-facing experience has two separate entry points:

- Prospect: `/app/?journey=prospect` opens card discovery with conditional value illustrations and local exploration actions.
- Card Member: `/app/?journey=member` opens the existing wallet, with dining/culture and shopping/hotel demo profiles under “Your travel style.”

The journey switch changes the active synthetic customer. Preferences remain saved independently for each customer. Technical details are collapsed under “How your experience is personalized”; recommendation evidence remains available on each item.

1. **Show understanding, not chat.** Start on A taste of culture. Explain that three permissioned events become a Rome planning intent. Expand the signal panel: `.10 + .45 + .40 = .95`, a rules-based score, not predictive probability.
2. **Make the recommendation concrete.** Savor is the top held card. Its dining and gallery benefits match fine dining and museums. Open Why you’re seeing this and show the preference, intent, catalog and rule evidence. Switch to Sanctuary to see only that held card's applicable content.
3. **Explain honest value.** Savor's USD 60 is the highest dining alternative (USD 40) plus the highest culture alternative (USD 20). The USD 30 dining offer and mock points are alternatives, not extra cash. Expand the calculation to show excluded rows. Experiential benefits have no invented price.
4. **Same trip, different person.** Switch to A considered escape. With the same held cards and different preferences, Sanctuary leads. USD 135 = mock stay credit USD 90 + the highest shopping offer USD 45. Places, benefits, offers and rewards change.
5. **Prove user control.** Remove shopping. The total becomes USD 90 and shopping recommendations disappear. Refresh/regenerate: the tag remains suppressed, including its historical signal contribution. Restore scenario preferences afterward.
6. **Prove safe abstention.** Disable personalization. The personalized experience is cleared. Turn it back on to recover the scenario. Restoring preferences alone never restores consent.
7. **Show the prospect journey.** Select Prospect, or use its direct link. This journey offers Savor, Wander and Sanctuary as fictional product concepts. Explore Card / Start application only show local messages; no application, approval or outbound action occurs.

## Mocked components

### Demonstrate intent forming from events

Expand **Shape your trip** in either journey. Choose exploring, culture planning, booked holiday, business stay, or repeated clicks; edit the dates and click **Build my Rome experience**. Every event is persisted through `POST /signals`; after each event the UI calls `/intents/detect` with only that replay's IDs. The timeline displays the backend's contribution, aggregate score, and stage. The final intent generates the displayed recommendations through `/companion`. Saved profile preferences remain in effect; edit them to demonstrate different recommendations. Business purpose changes context but does not invent business-specific catalog rules. Out-of-validity dates can produce abstention.

To demonstrate the same process programmatically with the local server running:

```sh
.venv/bin/python scripts/replay_intent.py
```

Expected progression: ad click `0.10 / exploring`, repeated click `0.10 / exploring`, flight search `0.55 / planning`, hotel search `0.95 / planning`, booking `1.00 / booked`. This is a rules score, not travel probability. Each replay uses new synthetic event IDs and retains an audit trail; it does not delete existing signals or change consent. It requires personalization permission on the dining profile.

All profiles, signal sources, cards, benefits, offers, points rules, conversion rates, merchants, acceptance facts, eligibility conditions and spending assumptions are synthetic JSON fixtures. The Rome illustration is a decorative schematic, not a map. Default AI ranking is deterministic; optional LLM transport is tested using HTTP mocks.

## Production evolution (not implemented)

Add identity and per-customer authorization before exposing the app beyond localhost. Establish consent provenance, retention/deletion rules, catalog ownership and verified fact ingestion. Replace the repository implementation with a managed relational database and migrations. Add rate limits, transaction isolation, deployment hardening and monitoring. Evaluate model ranking with an approved benchmark before enabling it, and add source adapters only for explicitly permissioned signals. Do not treat this prototype as approved for real financial decisions.

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { OutingPlanner } from "./OutingPlanner";
import {
  EvidenceDetails,
  RecommendationTile,
  ValuePanel,
} from "./Recommendations";
import { shortName } from "./format";
import { RomeIllustration } from "./RomeIllustration";
import { IntentStudio } from "./IntentStudio";
import { BusinessApp } from "./BusinessApp";
import { MobileNavigation } from "./JourneyShell";
import { IntentControls, MerchantLookup, SupplementaryExplore } from "./ExperienceControls";
import type {
  Customer,
  Detection,
  Experience,
  Preference,
  Scenario,
} from "./types";

const preferences: Preference[] = [
  "fine dining",
  "museums",
  "luxury hotels",
  "shopping",
  "dining",
  "culture",
];
const defaultPreferences: Record<string, Preference[]> = {
  prospect: ["dining", "culture"],
  dining: ["fine dining", "museums"],
  stay: ["shopping", "luxury hotels"],
};
type Collection = "benefits" | "offers" | "rewards" | "merchants";
type Journey = "prospect" | "member";
const currentJourney = (): Journey =>
  new URLSearchParams(window.location.search).get("journey") === "prospect"
    ? "prospect"
    : "member";

export function App() {
  return new URLSearchParams(window.location.search).get("journey") === "business" ? <BusinessApp /> : <ConsumerApp />;
}

function ConsumerApp() {
  const [journey, setJourney] = useState<Journey>(currentJourney);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [experience, setExperience] = useState<Experience | null>(null);
  const [detectedIntentId, setDetectedIntentId] = useState("");
  const [loading, setBusy] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const busy = loading || simulating;
  const [error, setError] = useState("");
  const [abstention, setAbstention] = useState<string[]>([]);
  const [card, setCard] = useState("");
  const [collection, setCollection] = useState<Collection>("benefits");
  const [notice, setNotice] = useState("");
  const [preferenceToAdd, setPreferenceToAdd] = useState("");
  const sequence = useRef(0);

  const loadScenario = useCallback(
    async (selected: Scenario, keepCustomer = false) => {
      const run = ++sequence.current;
      setScenario(selected);
      setBusy(true);
      setError("");
      setAbstention([]);
      setExperience(null);
      setDetectedIntentId("");
      if (!keepCustomer) setCustomer(null);
      setNotice("");
      try {
        const profile = await api<Customer>(
          `/customers/${selected.customer_id}`,
        );
        if (run !== sequence.current) return;
        setCustomer(profile);
        const detection = await api<Detection>("/intents/detect", "POST", {
          customer_id: selected.customer_id,
          signal_ids: selected.signal_ids,
        });
        if (run !== sequence.current) return;
        if (!detection.intent) {
          setAbstention(detection.abstention_reasons);
          return;
        }
        setDetectedIntentId(detection.intent.intent_id);
        const next = await api<Experience>("/companion", "POST", {
          customer_id: selected.customer_id,
          intent_id: detection.intent.intent_id,
        });
        if (run !== sequence.current) return;
        setExperience(next);
        setAbstention(next.abstention_reasons);
        setCard(next.recommended_cards[0]?.product_ids[0] || "");
      } catch (e) {
        if (run === sequence.current)
          setError(
            e instanceof Error ? e.message : "Unable to load the experience.",
          );
      } finally {
        if (run === sequence.current) setBusy(false);
      }
    },
    [],
  );

  useEffect(() => {
    let active = true;
    const generation = sequence;
    api<Scenario[]>("/scenarios")
      .then((items) => {
        if (!active) return;
        setScenarios(items);
        const initial =
          items.find(
            (s) =>
              s.scenario_id ===
              (currentJourney() === "prospect" ? "prospect" : "dining"),
          ) || items[0];
        if (initial) void loadScenario(initial);
        else {
          setError("No demo scenarios are available.");
          setBusy(false);
        }
      })
      .catch(() => {
        if (active) {
          setError(
            "Cannot reach the companion API. Check that the local server is running.",
          );
          setBusy(false);
        }
      });
    return () => {
      active = false;
      generation.current++;
    };
  }, [loadScenario]);

  const selectJourney = useCallback(
    (next: Journey) => {
      setJourney(next);
      setCollection("benefits");
      setPreferenceToAdd("");
      const selected = scenarios.find(
        (s) => s.scenario_id === (next === "prospect" ? "prospect" : "dining"),
      );
      if (selected) void loadScenario(selected);
    },
    [scenarios, loadScenario],
  );

  useEffect(() => {
    const onBack = () => selectJourney(currentJourney());
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, [selectJourney]);

  function switchJourney(next: Journey) {
    const url = new URL(window.location.href);
    url.searchParams.set("journey", next);
    window.history.pushState({}, "", url);
    selectJourney(next);
  }
  const isProspect = journey === "prospect";

  async function change(path: string, method: string, body: unknown) {
    if (!scenario || busy) return;
    const current = scenario;
    setBusy(true);
    setError("");
    setExperience(null);
    try {
      await api(path, method, body);
      await loadScenario(current);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save this change.");
      setBusy(false);
    }
  }

  const selectedCard = experience?.recommended_cards.find((r) =>
    r.product_ids.includes(card),
  );
  const selectedValue = experience?.value_summary.find(
    (v) => v.product_id === card,
  );
  const visible =
    experience?.[collection].filter((r) => r.product_ids.includes(card)) || [];
  const activePrefs =
    experience?.preferences_used || customer?.stated_preferences || [];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#top" aria-label="Intent Companion home">
          <span className="brand-mark">
            i<span>c</span>
          </span>
          <span>
            intent<span className="brand-sub">companion</span>
          </span>
        </a>
        <div className="workspace-label">THE TRAVEL EDIT</div>
        <nav aria-label="Main navigation">
          <a href="#top" className="nav-active">
            <span>◎</span> Your experience <span className="nav-arrow">↗</span>
          </a>
          <a href="#value">
            <span>◇</span> Value & evidence
          </a>
          <a href="#pipeline">
            <span>☷</span> Your personalization
          </a>
          <a href="#preferences">
            <span>⊙</span> Your preferences
          </a>
        </nav>
        <div className="sidebar-note">
          <span className="compass" aria-hidden="true">
            ✧
          </span>
          <h3>
            A little more you.
            <br />A lot more Rome.
          </h3>
          <p>
            Travel ideas shaped by your intent. Every recommendation has a
            reason.
          </p>
        </div>
        <div className="sidebar-footer">
          <span className="status-dot" /> Local demonstration
          <p>Illustrative AMEX value · No live bookings</p>
        </div>
      </aside>
      <main id="top">
        <header className="topbar">
          <a
            className="mobile-brand"
            href="#top"
            aria-label="Intent Companion home"
          >
            <span className="brand-mark">
              i<span>c</span>
            </span>
            <strong>intent companion</strong>
          </a>
          <div className="breadcrumb">
            Your companion <span>/</span> <strong>Rome</strong>
          </div>
          <span className="demo-badge">
            SYNTHETIC DEMO ·{" "}
            {experience?.provider_mode === "llm" ? "LLM" : "DETERMINISTIC"}
          </span>
        </header>
        <div className="journey-switch" aria-label="Choose your journey">
          <a className="business-entry" href="?journey=business"><strong>Small Business</strong><span>Build your next chapter</span></a>
          <button
            disabled={busy}
            aria-pressed={isProspect}
            onClick={() => switchJourney("prospect")}
          >
            <strong>Prospect</strong>
            <span>Discover your possibilities</span>
          </button>
          <button
            disabled={busy}
            aria-pressed={!isProspect}
            onClick={() => switchJourney("member")}
          >
            <strong>Card Member</strong>
            <span>Make more of your membership</span>
          </button>
        </div>
        <section className="page-heading">
          <div>
            <div className="eyebrow">
              {isProspect
                ? "YOUR NEXT CHAPTER STARTS HERE"
                : "WELCOME TO YOUR TRAVEL COMPANION"}
            </div>
            <h1>
              {isProspect
                ? "Find your kind of rewarding."
                : "Your cards. Your Rome."}
            </h1>
            <p>
              {isProspect
                ? "Explore a card that fits the way you love to travel."
                : "Discover what the cards you already hold can bring to your trip."}
            </p>
          </div>
          <span className="edition">
            01 <span>/ THE ROME EDITION</span>
          </span>
        </section>
        {!isProspect && (
          <section
            className="scenario-section"
            aria-label="Demo member profiles"
          >
            <div className="section-mini">
              Your travel style <span>Choose a demo member profile.</span>
            </div>
            <div className="scenario-grid">
              {scenarios
                .filter((s) => s.scenario_id !== "prospect")
                .map((s, i) => (
                  <button
                    key={s.scenario_id}
                    disabled={busy}
                    className={`scenario ${scenario?.scenario_id === s.scenario_id ? "selected" : ""}`}
                    onClick={() => {
                      setCollection("benefits");
                      void loadScenario(s);
                    }}
                    aria-pressed={scenario?.scenario_id === s.scenario_id}
                  >
                    <span className="scenario-number">0{i + 1}</span>
                    <span>
                      <strong>{s.title}</strong>
                      <small>{s.subtitle}</small>
                    </span>
                    <span className="scenario-arrow">↗</span>
                  </button>
                ))}
            </div>
          </section>
        )}
        <section className="trip-hero">
          <div className="hero-content">
            <span className="hero-kicker">
              <span />{" "}
              {isProspect ? "IMAGINE YOUR NEXT ESCAPE" : "YOUR UPCOMING ESCAPE"}
            </span>
            <h2>
              When in <em>Rome.</em>
            </h2>
            <p>
              {activePrefs.length
                ? `For your love of ${activePrefs.join(" & ")}.`
                : "A city of possibilities."}
              <br />
              {isProspect
                ? "See how a card could complement your plans."
                : "Let’s make the most of your membership."}
            </p>
            <div className="trip-meta">
              <span>
                {experience?.intent
                  ? `${experience.intent.start_date} — ${experience.intent.end_date}`
                  : "10 — 15 OCT 2026"}
              </span>
              <span>
                {experience?.intent?.intent_stage?.toUpperCase() ||
                  "TRIP PREVIEW"}
              </span>
              <span>
                {experience?.intent?.purpose.toUpperCase() || "LEISURE"}
              </span>
            </div>
          </div>
          <RomeIllustration />
          <div className="hero-coordinate">41.9028° N &nbsp; 12.4964° E</div>
        </section>
        {customer && <OutingPlanner key={`outing-${customer.customer_id}`} customer={customer} />}
        {customer && scenario && (
          <IntentStudio
            key={customer.customer_id}
            customer={customer}
            disabled={busy}
            onRunState={setSimulating}
            onApply={(ids) =>
              loadScenario({ ...scenario, signal_ids: ids }, true)
            }
          />
        )}
        {customer && detectedIntentId && scenario && <IntentControls owner={customer.customer_id} intent={detectedIntentId} onChange={() => loadScenario(scenario)} />}
        <div aria-live="polite" className="status-region">
          {busy && (
            <div className="loading">
              <span className="spinner" /> Preparing your personalized Rome
              experience…
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              {notice}
              <button
                onClick={() => setNotice("")}
                aria-label="Dismiss message"
              >
                ×
              </button>
            </div>
          )}
        </div>
        {error && (
          <div role="alert" className="error-box">
            <h3>We couldn’t complete that request.</h3>
            <p>{error}</p>
            {scenario && (
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => void loadScenario(scenario)}
              >
                Try again
              </button>
            )}
          </div>
        )}
        {!busy && abstention.length > 0 && (
          <section className="abstention">
            <span aria-hidden="true">◇</span>
            <h2>Trust comes before a recommendation.</h2>
            <p>No verified recommendation is available for this scenario.</p>
            <ul>
              {abstention.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <small>
              No facts or values have been invented. Update your controls below
              and regenerate.
            </small>
          </section>
        )}
        <div className="content-grid">
          <div className="primary-column">
            {experience?.status === "ready" && selectedCard && (
              <>
                <div className="section-heading">
                  <div>
                    <div className="eyebrow">
                      {customer?.lifecycle_stage === "prospect"
                        ? "A CARD TO EXPLORE"
                        : "ALREADY IN YOUR WALLET"}
                    </div>
                    <h2>
                      {isProspect
                        ? "A card for the way you travel."
                        : "Your best companion is already in your wallet."}
                    </h2>
                  </div>
                  <span className="verified">✓ Evidence-backed</span>
                </div>
                <p className="journey-context">
                  {isProspect
                    ? "Compare fictional card options for this trip. Benefits and potential values are conditional illustrations, subject to the displayed conditions."
                    : "Compare your held demo cards to see which fits each part of your trip."}
                </p>
                <div className="card-selector" aria-label="Compare demo cards">
                  {experience.recommended_cards.map((r, i) => (
                    <button
                      key={r.recommendation_id}
                      aria-pressed={card === r.product_ids[0]}
                      className={card === r.product_ids[0] ? "active" : ""}
                      onClick={() => setCard(r.product_ids[0])}
                    >
                      {shortName(r.title)}
                      {i === 0 && <span>Top match</span>}
                    </button>
                  ))}
                </div>
                <section className="card-feature">
                  <div
                    className={`payment-card ${card}`}
                    aria-label={`${shortName(selectedCard.title)} synthetic demo card`}
                  >
                    <span>INTENT COLLECTION</span>
                    <strong>{shortName(selectedCard.title)}</strong>
                    <div className="card-chip" aria-hidden="true" />
                    <div className="card-bottom">
                      <span>DEMO / NOT A PAYMENT CARD</span>
                      <span>✧</span>
                    </div>
                  </div>
                  <div className="card-copy">
                    <span className="eyebrow">
                      {customer?.lifecycle_stage === "prospect"
                        ? "CONTEXTUALLY RELEVANT"
                        : "YOUR HELD DEMO CARD"}
                    </span>
                    <h3>{shortName(selectedCard.title)}</h3>
                    <p>{selectedCard.description}</p>
                    <p className="card-reason">{selectedCard.explanation}</p>
                    {customer?.lifecycle_stage === "prospect" && (
                      <div className="mock-actions">
                        <button
                          className="button"
                          onClick={() =>
                            setNotice(
                              "Explore Card: this is a fictional concept product. No application or credit assessment takes place.",
                            )
                          }
                        >
                          Explore Card ↗
                        </button>
                        <button
                          className="text-button"
                          onClick={() =>
                            setNotice(
                              "Mock application only. Nothing has been submitted, and no credit decision has been made.",
                            )
                          }
                        >
                          Start application (mock)
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="card-evidence">
                    <EvidenceDetails recommendation={selectedCard} />
                  </div>
                </section>
                <div className="section-heading discoveries">
                  <div>
                    <div className="eyebrow">
                      LESS SEARCHING. MORE DISCOVERING.
                    </div>
                    <h2>
                      {isProspect
                        ? "Picture the possibilities."
                        : "Make the most of your Rome."}
                    </h2>
                  </div>
                </div>
                <div
                  className="collection-tabs"
                  aria-label="Recommendation category"
                >
                  {(
                    [
                      "benefits",
                      "offers",
                      "rewards",
                      "merchants",
                    ] as Collection[]
                  ).map((k) => (
                    <button
                      key={k}
                      aria-pressed={collection === k}
                      className={collection === k ? "active" : ""}
                      onClick={() => setCollection(k)}
                    >
                      {k === "merchants"
                        ? "Places"
                        : k.charAt(0).toUpperCase() + k.slice(1)}
                      <span>
                        {
                          experience[k].filter((r) =>
                            r.product_ids.includes(card),
                          ).length
                        }
                      </span>
                    </button>
                  ))}
                </div>
                <div className="recommendation-grid">
                  {visible.map((r) => (
                    <RecommendationTile
                      key={r.recommendation_id}
                      recommendation={r}
                      card={card}
                    />
                  ))}
                </div>
                {!visible.length && (
                  <div className="empty-state">
                    No verified{" "}
                    {collection === "merchants" ? "places" : collection} match
                    this card and your current preferences.
                  </div>
                )}
              </>
            )}
            <details className="pipeline-panel" id="pipeline">
              <summary className="personalization-summary">
                How your experience is personalized{" "}
                <span>Explore the details</span>
              </summary>
              <div className="section-heading">
                <div>
                  <div className="eyebrow">NOT A BLACK BOX</div>
                  <h2>From a signal to something useful.</h2>
                </div>
              </div>
              <div className="pipeline">
                {(experience?.trace.length
                  ? experience.trace
                  : [
                      {
                        stage: "Detect",
                        description:
                          "Receive and normalize permissioned signals.",
                        count: 0,
                      },
                      {
                        stage: "Understand",
                        description:
                          "Separate your trip intent from your customer context.",
                        count: 0,
                      },
                      {
                        stage: "Activate",
                        description:
                          "Apply rules, calculate value, then rank approved choices.",
                        count: 0,
                      },
                    ]
                ).map((step, i) => (
                  <div className="pipeline-step" key={step.stage}>
                    <span className="step-number">0{i + 1}</span>
                    <h3>{step.stage}</h3>
                    <p>{step.description}</p>
                  </div>
                ))}
              </div>
              {experience?.intent && (
                <details className="signal-details">
                  <summary>
                    Inspect signals & confidence{" "}
                    <span>
                      {Math.round(experience.intent.confidence * 100)} / 100 ·
                      rules-based score
                    </span>
                  </summary>
                  <p>
                    Sum of configured weights, capped at 1. Each signal type
                    contributes once per trip. This is not an ML probability.
                  </p>
                  {experience.intent.evidence.map((e) => (
                    <div className="signal-row" key={e.evidence_id}>
                      <span>
                        {e.fact}
                        <small>{e.source_id}</small>
                      </span>
                      <code>+{e.weight?.toFixed(2)}</code>
                    </div>
                  ))}
                  <p>
                    Intent expires:{" "}
                    {new Date(experience.intent.expires_at).toLocaleString(
                      "en-GB",
                      { timeZone: "UTC" },
                    )}{" "}
                    UTC. Demo clock: 17 Sep 2026.
                  </p>
                </details>
              )}
              <div className="provider-label">
                <span className="status-dot" />{" "}
                {experience?.provider_mode === "llm"
                  ? "LLM ranking · catalog-grounded wording"
                  : "Deterministic ranking · no model required"}
                {experience?.fallback_reason && (
                  <p>{experience.fallback_reason}</p>
                )}
              </div>
            </details>
          </div>
          <aside className="context-column">
            {customer && <MerchantLookup key={`${customer.customer_id}-${customer.consent.allowed}`} owner={customer.customer_id} />}
            {customer?.consent.allowed && <SupplementaryExplore />}
            {experience?.status === "ready" && selectedCard && (
              <ValuePanel
                value={selectedValue}
                title={shortName(selectedCard.title)}
              />
            )}
            <section className="preferences-panel" id="preferences">
              <span className="eyebrow">PERSONAL, ON YOUR TERMS</span>
              <h2>What makes it yours.</h2>
              <p>
                Your active preferences shape these recommendations. You’re in
                control.
              </p>
              <div className="preference-chips">
                {activePrefs.map((p) => (
                  <button
                    key={p}
                    disabled={busy}
                    title={`Remove ${p}`}
                    aria-label={`Remove ${p}`}
                    onClick={() =>
                      void change(
                        `/customers/${customer?.customer_id}/preferences/remove`,
                        "POST",
                        { preference: p },
                      )
                    }
                  >
                    {p}
                    <span>×</span>
                  </button>
                ))}
                {!activePrefs.length && <small>No active preferences.</small>}
              </div>
              <form
                className="preference-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (preferenceToAdd && customer) {
                    void change(
                      `/customers/${customer.customer_id}/preferences`,
                      "PUT",
                      { preferences: [...activePrefs, preferenceToAdd] },
                    );
                    setPreferenceToAdd("");
                  }
                }}
              >
                <label className="sr-only" htmlFor="add-preference">
                  Add a preference
                </label>
                <select
                  id="add-preference"
                  disabled={busy || !customer}
                  value={preferenceToAdd}
                  onChange={(e) => setPreferenceToAdd(e.target.value)}
                >
                  <option value="">Add a preference…</option>
                  {preferences
                    .filter((p) => !activePrefs.includes(p))
                    .map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                </select>
                <button
                  disabled={busy || !preferenceToAdd}
                  className="add-button"
                  aria-label="Add selected preference"
                >
                  +
                </button>
              </form>
              {customer?.suppressed_preferences.length ? (
                <p className="suppressed">
                  Removed preferences stay suppressed—even in past signals.
                </p>
              ) : null}
              <div className="consent-row">
                <label htmlFor="consent">
                  Allow personalization
                  <small>Applies before any signal is used</small>
                </label>
                <input
                  id="consent"
                  type="checkbox"
                  disabled={busy || !customer}
                  checked={customer?.consent.allowed || false}
                  onChange={(e) =>
                    void change(
                      `/customers/${customer?.customer_id}/consent`,
                      "PUT",
                      { allowed: e.target.checked, purpose: "personalization" },
                    )
                  }
                />
              </div>
              <button
                className="button secondary full-width"
                disabled={busy || !scenario}
                onClick={() => scenario && void loadScenario(scenario)}
              >
                Regenerate experience ↻
              </button>
              <button
                className="text-button reset-preferences"
                disabled={busy || !scenario}
                onClick={() =>
                  scenario &&
                  void change(
                    `/customers/${scenario.customer_id}/preferences`,
                    "PUT",
                    { preferences: defaultPreferences[scenario.scenario_id] },
                  )
                }
              >
                Restore scenario preferences
              </button>
            </section>
            <div className="trust-note">
              <span aria-hidden="true">✓</span>
              <div>
                <strong>Grounded, not guessed.</strong>
                <p>
                  Only verified mock catalog items. If evidence is missing, we
                  hold the recommendation.
                </p>
              </div>
            </div>
          </aside>
        </div>
        <footer className="main-footer">
          <span>
            intent companion <span> / </span> Built around you.
          </span>
          <p>
            Demo customers, cards, benefits and values are fictional. Outing places follow the mode shown above.
            No credit decisions. No live bookings.
          </p>
        </footer>
        <MobileNavigation />
      </main>
    </div>
  );
}

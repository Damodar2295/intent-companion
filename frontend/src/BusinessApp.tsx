import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { BusinessShell } from "./JourneyShell";
import { IntentControls, MerchantLookup } from "./ExperienceControls";
import type {
  BExperience,
  BIntent,
  Business,
  BusinessScenario,
  Category,
  Draft,
  Goal,
  Signal,
} from "./businessTypes";

const categories: Category[] = [
  "ingredients",
  "packaging",
  "equipment",
  "software",
  "travel",
  "employees",
];
const usd = (amount: string | number = 0) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(Number(amount));

export function BusinessApp() {
  const [scenarios, setScenarios] = useState<BusinessScenario[]>([]);
  const [scenario, setScenario] = useState<BusinessScenario | null>(null);
  const [profile, setProfile] = useState<Business | null>(null);
  const [intent, setIntent] = useState<BIntent | null>(null);
  const [experience, setExperience] = useState<BExperience | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [goalText, setGoalText] = useState("");
  const [goalType, setGoalType] = useState<Goal>("expansion");
  const [priorities, setPriorities] = useState<Category[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [card, setCard] = useState("");
  const [notice, setNotice] = useState("");
  const run = useRef(0);

  const load = useCallback(
    async (selected: BusinessScenario, ids = selected.signal_ids) => {
      const generation = ++run.current;
      setBusy(true);
      setError("");
      setExperience(null);
      setIntent(null);
      try {
        const customer = await api<Business>(
          `/businesses/${selected.business_id}`,
        );
        if (generation !== run.current) return;
        setProfile(customer);
        setPriorities(customer.priorities);
        setScenario({ ...selected, signal_ids: ids });
        const detection = await api<{
          intent: BIntent | null;
          abstention_reasons: string[];
        }>("/business/intents/detect", "POST", {
          business_id: selected.business_id,
          goal_id: selected.goal_id,
          signal_ids: ids,
        });
        if (generation !== run.current) return;
        if (!detection.intent) {
          setError(detection.abstention_reasons.join(" "));
          return;
        }
        setIntent(detection.intent);
        setGoalType(detection.intent.goal_type);
        const input = await api<Signal[]>(
          `/business/intents/${detection.intent.intent_id}/signals?business_id=${selected.business_id}`,
        );
        const result = await api<BExperience>("/business/companion", "POST", {
          business_id: selected.business_id,
          intent_id: detection.intent.intent_id,
        });
        if (generation !== run.current) return;
        setSignals(input);
        setExperience(result);
        setCard(result.products[0]?.item_id || "");
      } catch (e) {
        if (generation === run.current)
          setError(
            e instanceof Error
              ? e.message
              : "Unable to load business experience.",
          );
      } finally {
        if (generation === run.current) setBusy(false);
      }
    },
    [],
  );

  useEffect(() => {
    const generationCounter = run;
    let active = true;
    void api<BusinessScenario[]>("/business/scenarios")
      .then((items) => {
        if (!active) return;
        setScenarios(items);
        const id =
          new URLSearchParams(location.search).get("scenario") || "bakery";
        const selected = items.find((s) => s.scenario_id === id) || items[0];
        if (selected) {
          setGoalText(selected.goal_text);
          void load(selected);
        } else {
          setError("No business scenarios available.");
          setBusy(false);
        }
      })
      .catch(() => {
        if (active) {
          setError(
            "Unable to reach the business API. Restart the backend after upgrading.",
          );
          setBusy(false);
        }
      });
    return () => {
      active = false;
      generationCounter.current++;
    };
  }, [load]);

  async function generate() {
    if (!profile || !scenario) return;
    setBusy(true);
    setError("");
    setExperience(null);
    try {
      const health = await api<{ clock: string }>("/health");
      await api(`/businesses/${profile.business_id}/preferences`, "PUT", {
        priorities,
      });
      const ids: string[] = [];
      const inputs = [...signals];
      for (const category of priorities)
        if (!inputs.some((s) => s.category === category))
          inputs.push({
            ...signals[0],
            category,
            spend: null,
            event_type: "supplier_search",
          });
      for (const [index, signal] of inputs.entries()) {
        const id = `business-ui-${crypto.randomUUID()}`;
        await api("/business/signals", "POST", {
          ...signal,
          event_id: id,
          goal_type: goalType,
          consent: profile.consent,
          timestamp: new Date(
            Date.parse(health.clock) - (inputs.length - index) * 1000,
          ).toISOString(),
        });
        ids.push(id);
      }
      await load(scenario, ids);
      setNotice(
        "Your experience has been rebuilt from the updated synthetic inputs.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update scenario.");
      setBusy(false);
    }
  }

  async function extract() {
    if (!profile) return;
    setBusy(true);
    setError("");
    setDraft(null);
    setReviewed(false);
    try {
      setDraft(
        await api<Draft>("/business/goals/extract", "POST", {
          business_id: profile.business_id,
          text: goalText,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to extract a draft.");
    } finally {
      setBusy(false);
    }
  }

  async function consent(allowed: boolean) {
    if (!profile || !scenario) return;
    setBusy(true);
    setExperience(null);
    setIntent(null);
    setDraft(null);
    try {
      await api(`/businesses/${profile.business_id}/consent`, "PUT", {
        allowed,
        purpose: "personalization",
      });
      await load(scenario);
    } catch {
      setError("Unable to change consent.");
      setBusy(false);
    }
  }

  const totals = experience?.totals_by_product[card];
  const recommendations =
    experience?.recommendations.filter((r) => r.product_ids.includes(card)) ||
    [];
  return (
    <BusinessShell provider={experience?.provider_mode || "deterministic"}>
      <section className="business-heading">
        <div>
          <span className="eyebrow">THE BUSINESS EDIT</span>
          <h1>Built for your next move.</h1>
          <p>Turn your business plans into opportunities you can understand.</p>
        </div>
        <span className="edition">02 / BUSINESS</span>
      </section>
      <div className="business-scenarios">
        {scenarios.map((s) => (
          <button
            key={s.scenario_id}
            disabled={busy}
            className={
              scenario?.scenario_id === s.scenario_id ? "selected" : ""
            }
            onClick={() => {
              const url = new URL(location.href);
              url.searchParams.set("scenario", s.scenario_id);
              history.replaceState({}, "", url);
              setDraft(null);
              setNotice("");
              setGoalText(s.goal_text);
              void load(s);
            }}
          >
            <strong>
              {s.scenario_id === "bakery"
                ? "Northstar Bakery"
                : "Fieldwork Consulting"}
            </strong>
            <span>{s.subtitle}</span>
          </button>
        ))}
      </div>
      <section className="business-hero">
        <div>
          <span className="hero-kicker">
            {profile?.name || "YOUR BUSINESS COMPANION"}
          </span>
          <h2>{scenario?.title || "Room to grow."}</h2>
          <p>{scenario?.subtitle}</p>
          <div className="business-hero-tags">
            <span>
              {intent?.goal_type.replaceAll("_", " ") || "Business intent"}
            </span>
            <span>{intent?.intent_stage || "Preparing"}</span>
            <span>US · USD</span>
          </div>
        </div>
        <div className="business-hero-aside">
          <span>YOUR NEXT CHAPTER</span>
          <strong>
            {intent ? `${Math.round(intent.confidence * 100)}` : "—"}
            <small>/100</small>
          </strong>
          <p>
            Intent strength · rules-based
            <br />
            {intent?.confirmation || "Awaiting evidence"}
          </p>
        </div>
      </section>
      {busy && (
        <p className="loading" role="status">
          Building your business experience…
        </p>
      )}
      {error && (
        <div className="error-box" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {intent && profile && scenario && (
        <IntentControls
          owner={profile.business_id}
          intent={intent.intent_id}
          business
          status={intent.confirmation}
          onChange={() => load(scenario)}
        />
      )}
      {experience?.status === "abstained" && (
        <section className="abstention">
          <h2>We need verified, permitted evidence.</h2>
          {experience.abstention_reasons.map((r) => (
            <p key={r}>{r}</p>
          ))}
        </section>
      )}
      {experience?.status === "ready" && (
        <>
          <section className="business-stats" aria-label="Spend overview">
            {[
              ["observed_spend", "Observed spend"],
              ["planned_spend", "Planned spend"],
              [
                "potential_card_addressable_spend",
                "Potential card-addressable spend",
              ],
            ].map(([key, title]) => (
              <article key={key}>
                <span>{title}</span>
                <strong>{usd(experience.spend_summary[key])}</strong>
                <p>
                  {key === "potential_card_addressable_spend"
                    ? "Verified supplier/category fit; not savings or guaranteed conversion."
                    : "Across the distinct periods shown below; not an annual forecast."}
                </p>
              </article>
            ))}
          </section>
          <div className="business-columns">
            <section>
              <div className="section-heading">
                <div>
                  <span className="eyebrow">
                    FROM YOUR PLANS TO POSSIBILITIES
                  </span>
                  <h2>Opportunities for your next chapter.</h2>
                </div>
              </div>
              <div className="card-selector">
                {experience.products.map((p) => (
                  <button
                    key={p.item_id}
                    className={card === p.item_id ? "active" : ""}
                    aria-pressed={card === p.item_id}
                    onClick={() => setCard(p.item_id)}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
              <div className="business-opportunities">
                {recommendations.map((r) => (
                  <article
                    className="recommendation-tile"
                    key={r.recommendation_id}
                  >
                    <span className="eyebrow">
                      {r.category} · {r.supplier}
                    </span>
                    <h3>{r.title}</h3>
                    <p>{r.description}</p>
                    {r.values
                      .filter((v) => v.product_id === card)
                      .map((v) => (
                        <div
                          className="business-value-line"
                          key={`${v.observation_id}-${v.product_id}`}
                        >
                          <strong>{usd(v.amount)}</strong>
                          <span>
                            potential {v.value_type} ·{" "}
                            {v.included_in_total ? "included" : "alternative"}
                          </span>
                        </div>
                      ))}
                    {r.value_note && <p>{r.value_note}</p>}
                    <details>
                      <summary>Why you’re seeing this</summary>
                      {r.evidence.map((e, i) => (
                        <p key={i}>
                          {e.fact}
                          <small className="source-label">
                            {e.origin} · {e.source_id}
                          </small>
                        </p>
                      ))}
                    </details>
                    <details>
                      <summary>Conditions & calculation</summary>
                      <ul>
                        {r.conditions.map((c) => (
                          <li key={c}>{c}</li>
                        ))}
                      </ul>
                      {r.values
                        .filter((v) => v.product_id === card)
                        .map((v) => (
                          <div key={v.observation_id}>
                            <p>{v.calculation_rule}</p>
                            <p>
                              {v.period} · {v.exclusion_reason}
                            </p>
                            {v.assumptions.map((a) => (
                              <p key={a}>{a}</p>
                            ))}
                          </div>
                        ))}
                    </details>
                    <button
                      className="text-button"
                      onClick={() =>
                        setNotice(
                          `Exploring ${r.title}. Local demo only; no supplier contact, payment or application occurs.`,
                        )
                      }
                    >
                      Explore opportunity ↗
                    </button>
                  </article>
                ))}
              </div>
              {!recommendations.length && (
                <p className="empty-state">
                  No verified opportunities for this card and your current
                  priorities.
                </p>
              )}
            </section>
            <aside id="value" className="business-value-panel">
              <span className="eyebrow">POTENTIAL VALUE · SELECTED CARD</span>
              <h2>{usd(totals?.savings)}</h2>
              <p>Illustrative savings</p>
              <h3>{usd(totals?.rewards)}</h3>
              <p>Illustrative reward value</p>
              <hr />
              <p>
                Card alternatives are separate. Figures assume qualifying spend;
                fees are not modeled. Review each period and calculation before
                comparing.
              </p>
              <a href="#preferences" className="button secondary">
                Adjust your inputs
              </a>
            </aside>
          </div>
        </>
      )}
      <section className="business-editor" id="preferences">
        <div className="section-heading">
          <div>
            <span className="eyebrow">YOUR BUSINESS. YOUR CONTROLS.</span>
            <h2>Shape the next chapter.</h2>
          </div>
        </div>
        <label className="shared-interest">
          <input
            type="checkbox"
            checked={profile?.consent.allowed || false}
            disabled={busy || !profile}
            onChange={(e) => void consent(e.target.checked)}
          />{" "}
          Allow business personalization
        </label>
        {profile?.consent.allowed && (
          <>
            <label className="goal-label">
              Describe your business goal
              <textarea
                value={goalText}
                maxLength={2000}
                onChange={(e) => {
                  setGoalText(e.target.value);
                  setDraft(null);
                  setReviewed(false);
                }}
              />
            </label>
            <button
              className="button secondary"
              disabled={busy || !goalText.trim()}
              onClick={() => void extract()}
            >
              Prepare a goal draft
            </button>
            {draft && (
              <div className="draft-review">
                <span className="eyebrow">DRAFT · {draft.provider_mode}</span>
                <h3>
                  {draft.goal_type?.replaceAll("_", " ") ||
                    "Tell us more about your goal"}
                </h3>
                <p>
                  {draft.categories.join(", ") || "Choose priorities below."}
                </p>
                <p>{draft.time_horizon || "No time horizon stated."}</p>
                <p>{draft.explanation}</p>
                <p>Supporting words: {draft.evidence_excerpts.join(" · ")}</p>
                <label className="shared-interest">
                  <input
                    type="checkbox"
                    checked={reviewed}
                    onChange={(e) => setReviewed(e.target.checked)}
                  />{" "}
                  I have reviewed this draft
                </label>
                <button
                  className="button secondary"
                  disabled={
                    !reviewed || !draft.goal_type || draft.needs_clarification
                  }
                  onClick={() => {
                    setGoalType(draft.goal_type!);
                    setPriorities(draft.categories);
                    setDraft(null);
                    setNotice(
                      "Draft applied to the editor. Rebuild the experience to save it.",
                    );
                  }}
                >
                  Use reviewed draft
                </button>
              </div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void generate();
              }}
            >
              <label className="goal-label">
                Goal category
                <select
                  value={goalType}
                  onChange={(e) => setGoalType(e.target.value as Goal)}
                >
                  <option value="expansion">Expansion</option>
                  <option value="client_growth">Client growth</option>
                  <option value="replenishment">Replenishment</option>
                </select>
              </label>
              <fieldset>
                <legend>Your priorities</legend>
                <div className="priority-options">
                  {categories.map((c) => (
                    <label key={c}>
                      <input
                        type="checkbox"
                        checked={priorities.includes(c)}
                        onChange={(e) =>
                          setPriorities(
                            e.target.checked
                              ? [...priorities, c]
                              : priorities.filter((p) => p !== c),
                          )
                        }
                      />
                      {c}
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="spend-editor">
                {signals
                  .filter((s) => s.spend)
                  .map((s) => (
                    <article key={s.event_id}>
                      <h3>{s.spend!.category}</h3>
                      <p>
                        {s.spend!.status} · {s.spend!.period_start} –{" "}
                        {s.spend!.period_end}
                      </p>
                      <label>
                        Amount (USD)
                        <input
                          type="number"
                          required
                          min="0"
                          max="9999999999"
                          step="0.01"
                          value={s.spend!.amount}
                          onChange={(e) =>
                            setSignals(
                              signals.map((item) =>
                                item.event_id === s.event_id
                                  ? {
                                      ...item,
                                      spend: {
                                        ...item.spend!,
                                        amount: e.target.value,
                                      },
                                    }
                                  : item,
                              ),
                            )
                          }
                        />
                      </label>
                      <label>
                        Payment method
                        <select
                          value={s.spend!.payment_method}
                          onChange={(e) =>
                            setSignals(
                              signals.map((item) =>
                                item.event_id === s.event_id
                                  ? {
                                      ...item,
                                      spend: {
                                        ...item.spend!,
                                        payment_method: e.target.value as
                                          "other" | "held_card" | "undecided",
                                      },
                                    }
                                  : item,
                              ),
                            )
                          }
                        >
                          <option value="held_card">Held business card</option>
                          <option value="other">Another payment method</option>
                          <option value="undecided">Undecided</option>
                        </select>
                      </label>
                    </article>
                  ))}
              </div>
              <button className="button" disabled={busy || !signals.length}>
                Rebuild my business experience
              </button>
            </form>
          </>
        )}
      </section>
      {profile && (
        <MerchantLookup
          key={`${profile.business_id}-${profile.consent.allowed}`}
          owner={profile.business_id}
          business
        />
      )}
      <details className="pipeline-panel" id="pipeline">
        <summary>
          Behind your experience{" "}
          <span>Presenter evidence and demonstration sequence</span>
        </summary>
        <ol className="business-trace">
          {(experience?.trace || []).map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        {intent?.evidence.map((e, i) => (
          <div className="signal-row" key={i}>
            <span>
              {e.fact}
              <small>
                {e.origin} · {e.source_id}
              </small>
            </span>
            <code>+{e.weight.toFixed(2)}</code>
          </div>
        ))}
        {experience?.exclusions.map((e) => (
          <p key={e}>{e}</p>
        ))}
        <p>
          Demo sequence: inspect the goal → compare spend and potential value →
          change packaging payment method → look up a supplier → dismiss and
          restore intent → switch to consultancy.
        </p>
        <p>
          Scheduled activity indicates commitment; intent strength is a
          heuristic score, not a probability.
        </p>
      </details>
    </BusinessShell>
  );
}

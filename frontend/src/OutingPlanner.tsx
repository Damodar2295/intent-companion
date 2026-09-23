import { useEffect, useRef, useState } from "react";
import { api, getGroundedOutingResponse, streamOuting } from "./api";
import type {
  Customer,
  OutingEvent,
  OutingResult,
  OutingEvidence,
} from "./types";

function Evidence({ items }: { items: OutingEvidence[] }) {
  return (
    <details className="outing-evidence">
      <summary>Sources & field evidence ({items.length})</summary>
      {items.map((e) => (
        <div key={e.evidence_id}>
          <strong>{e.field.replaceAll("_", " ")}</strong>
          <p>
            {typeof e.value === "object"
              ? JSON.stringify(e.value)
              : String(e.value)}
          </p>
          {e.url.startsWith("https://") ? (
            <a href={e.url} target="_blank" rel="noreferrer">
              {e.attribution || e.provider}
            </a>
          ) : (
            <span>Fictional demonstration</span>
          )}
          <small>
            {e.source_type} · Evidence strength {Math.round(e.confidence * 100)}
            /100 (not statistical certainty)
            <br />
            Checked {new Date(e.retrieved_at).toLocaleString()} · Expires{" "}
            {new Date(e.expires_at).toLocaleString()}
          </small>
        </div>
      ))}
    </details>
  );
}

export function OutingPlanner({ customer }: { customer: Customer }) {
  const [mode, setMode] = useState("");
  const [intent, setIntent] = useState(
    "Find an evening event, dining and shopping in Rome",
  );
  const [city, setCity] = useState("Rome");
  const [date, setDate] = useState(
    new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" }).format(
      new Date(),
    ),
  );
  const [timezone, setTimezone] = useState("Europe/Rome");
  const [start, setStart] = useState("17:00");
  const [end, setEnd] = useState("23:00");
  const [transport, setTransport] = useState("WALK");
  const [budget, setBudget] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [minutes, setMinutes] = useState(60);
  const [card, setCard] = useState(customer.existing_cards[0] || "card-a");
  const [origin, setOrigin] = useState<{ lat: number; lng: number } | null>(
    null,
  );
  const [conditions, setConditions] = useState<string[]>([]);
  const [events, setEvents] = useState<OutingEvent[]>([]);
  const [result, setResult] = useState<OutingResult | null>(null);
  const [active, setActive] = useState(0);
  const [error, setError] = useState("");
  const [grounded, setGrounded] = useState<import("./types").GroundedResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const context = JSON.stringify([
    customer.customer_id,
    customer.consent.allowed,
    customer.stated_preferences,
    customer.suppressed_preferences,
  ]);
  const contextRef = useRef(context);
  contextRef.current = context;
  useEffect(() => {
    api<{ mode: string }>("/outing/capabilities")
      .then((v) => setMode(v.mode))
      .catch(() => setMode("unavailable"));
  }, []);
  useEffect(() => {
    controller.current?.abort();
    setResult(null);
    setGrounded(null);
    setEvents([]);
    setBusy(false);
    setConditions([]);
    setOrigin(null);
    setCard(customer.existing_cards[0] || "card-a");
    return () => controller.current?.abort();
    // Context is the canonical invalidation key; preferences are deliberately not retained between contexts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context]);
  useEffect(() => {
    if (!result) return;
    const timer = window.setTimeout(
      () => {
        setResult(null);
        setError(
          "This outing has expired. Replan to refresh provider evidence.",
        );
      },
      Math.max(0, new Date(result.expires_at).getTime() - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [result]);
  async function run() {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const timeout = window.setTimeout(() => abort.abort(), 125000);
    setBusy(true);
    setError("");
    setResult(null);
    setGrounded(null);
    setEvents([]);
    setActive(0);
    try {
      await streamOuting(
        {
          customer_id: customer.customer_id,
          text: intent,
          city,
          date,
          timezone,
          start_time: start,
          end_time: end,
          travel_mode: transport,
          budget: budget || null,
          currency,
          visit_minutes: minutes,
          card_id: card || null,
          user_location: origin,
          confirmed_condition_ids: conditions,
        },
        abort.signal,
        (event) => {
          if (abort.signal.aborted) return;
          setEvents((prev) => [...prev, event]);
          if (event.result) setResult(event.result);
        },
      );
    } catch (e) {
      if (controller.current === abort)
        setError(
          abort.signal.aborted
            ? "Planning cancelled."
            : e instanceof Error
              ? e.message
              : "Planning failed.",
        );
    } finally {
      window.clearTimeout(timeout);
      if (controller.current === abort) setBusy(false);
    }
  }
  function locate() {
    if (!navigator.geolocation) {
      setError("Location is unavailable. You can still route between stops.");
      return;
    }
    const key = context;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (key === contextRef.current)
          setOrigin({
            lat: position.coords.latitude,
            lng: position.coords.longitude,
          });
      },
      () =>
        setError(
          "Location was not shared. Routes will start between selected stops.",
        ),
      { timeout: 8000 },
    );
  }
  const alternative = result?.alternatives[active];
  const zone = result?.search_plan?.timezone || timezone;
  const clock = (v: string) =>
    new Date(v).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: zone,
    });
  return (
    <section className="outing-panel" aria-labelledby="outing-heading">
      <div className="outing-heading">
        <div>
          <span className="eyebrow">YOUR NEXT FEW HOURS</span>
          <h2 id="outing-heading">An outing, made for you</h2>
          <p>
            Discover dining, culture, shopping and events. See the evidence
            behind every stop.
          </p>
        </div>
        <span className="outing-mode">
          {mode === "demo"
            ? "Offline demonstration"
            : mode === "realtime"
              ? "Realtime providers"
              : "Checking providers…"}
        </span>
      </div>
      <form
        onChange={() => {
          if (!busy) setResult(null);
        }}
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <label className="outing-intent">
          What would you like to do?
          <textarea
            required
            minLength={3}
            maxLength={1500}
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
          />
        </label>
        <div className="outing-fields">
          <label>
            Destination
            <input
              required
              value={city}
              onChange={(e) => {
                setCity(e.target.value);
                const zones: Record<string, string> = {
                  rome: "Europe/Rome",
                  roma: "Europe/Rome",
                  paris: "Europe/Paris",
                  london: "Europe/London",
                  "new york": "America/New_York",
                  tokyo: "Asia/Tokyo",
                };
                setTimezone(zones[e.target.value.toLowerCase().trim()] || "");
              }}
            />
          </label>
          <label>
            Date
            <input
              required
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </label>
          <label>
            Destination timezone
            <input
              required
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              list="outing-zones"
            />
            <datalist id="outing-zones">
              <option>Europe/Rome</option>
              <option>Europe/Paris</option>
              <option>America/New_York</option>
              <option>Asia/Tokyo</option>
            </datalist>
          </label>
          <label>
            From
            <input
              required
              type="time"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
          <label>
            Until
            <input
              required
              type="time"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </label>
          <label>
            Getting around
            <select
              value={transport}
              onChange={(e) => setTransport(e.target.value)}
            >
              <option value="WALK">Walking</option>
              <option value="TRANSIT">Public transport</option>
              <option value="DRIVE">Driving</option>
            </select>
          </label>
          <label>
            Budget (optional)
            <input
              type="number"
              min="1"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
            />
          </label>
          <label>
            Budget currency
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
            >
              <option>EUR</option>
              <option>USD</option>
              <option>GBP</option>
            </select>
          </label>
          <label>
            Assumed minutes per visit
            <input
              type="number"
              required
              min="15"
              max="180"
              value={minutes}
              onChange={(e) => setMinutes(Number(e.target.value))}
            />
          </label>
          <label>
            {customer.lifecycle_stage === "prospect"
              ? "Hypothetical card comparison"
              : "Evaluate a held card"}
            <select
              value={card}
              onChange={(e) => {
                setCard(e.target.value);
                setConditions([]);
              }}
            >
              {(customer.lifecycle_stage === "prospect"
                ? ["card-a", "card-b", "card-c"]
                : customer.existing_cards
              ).map((c) => (
                <option key={c} value={c}>
                  {c} · illustrative product
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="outing-actions">
          <button type="submit" disabled={busy || !customer.consent.allowed}>
            Plan my outing
          </button>
          {busy && (
            <button type="button" onClick={() => controller.current?.abort()}>
              Cancel
            </button>
          )}
          <button
            type="button"
            disabled={!customer.consent.allowed}
            onClick={locate}
          >
            {origin
              ? "Location shared for this run"
              : "Use my location (optional)"}
          </button>
          {origin && (
            <button type="button" onClick={() => setOrigin(null)}>
              Remove location
            </button>
          )}
        </div>
        <p className="outing-note">
          {!customer.consent.allowed
            ? "Enable personalization consent to continue. "
            : ""}
          Without an origin, routes begin between stops. Visit durations are
          editable planning assumptions. Fetched data is not live inventory.
        </p>
      </form>
      {events.length > 0 && (
        <div className="outing-progress" role="status" aria-live="polite">
          <strong>
            {busy ? events.at(-1)?.message : result?.status || "Stopped"}
          </strong>
          <ol>
            {events.map((e) => (
              <li key={e.sequence}>{e.message}</li>
            ))}
          </ol>
        </div>
      )}
      {error && (
        <p role="alert" className="outing-warning">
          {error}
        </p>
      )}
      {result && (
        <div className="outing-result">
          {result.hypothetical && (
            <p className="outing-warning">
              Hypothetical product comparison — this does not establish
              eligibility or entitlement.
            </p>
          )}
          {result.mode === "demo" && (
            <p className="outing-warning">
              Fictional places and routes for demonstration. All AMEX value is
              illustrative.
            </p>
          )}
          {result.warnings.map((w) => (
            <p className="outing-note" key={w}>
              {w}
            </p>
          ))}
          <div
            className="outing-tabs"
            role="group"
            aria-label="Outing alternatives"
          >
            {result.alternatives.map((_, i) => (
              <button
                key={i}
                aria-pressed={active === i}
                onClick={() => setActive(i)}
              >
                Option {i + 1}
              </button>
            ))}
          </div>
          {alternative && (
            <>
              <button
                type="button"
                onClick={() =>
                  getGroundedOutingResponse(result.outing_id)
                    .then(setGrounded)
                    .catch((e) =>
                      setError(e instanceof Error ? e.message : "Grounded response unavailable."),
                    )
                }
              >
                Show sourced summary
              </button>
              {grounded && (
                <p className="outing-note">
                  {grounded.summary} · {grounded.evidence_ids.length} evidence references
                </p>
              )}
              <div className="outing-value">
                <h3>Value found for this outing</h3>
                <p>Demo / illustrative AMEX value · {card}</p>
                <strong>
                  {Object.entries(alternative.totals_by_currency)
                    .map(([c, v]) => `${c} ${v}`)
                    .join(" · ") || "No confirmed cash value"}
                </strong>
                <span>
                  {alternative.reward_points} reward points · valued separately
                </span>
                <small>
                  Only confirmed conditions and selected stops count.
                  Alternatives are never added together.
                </small>
              </div>
              <p>
                {alternative.feasibility === "CHECKED"
                  ? "Schedule checks completed"
                  : "Feasibility incomplete — confirm hours, prices and availability"}
              </p>
              <ol className="outing-timeline">
                {alternative.stops.map((stop, i) => (
                  <li key={stop.entity.entity_id}>
                    <div className="outing-time">
                      {clock(stop.arrival)}
                      <span>{clock(stop.departure)}</span>
                    </div>
                    <article>
                      <span className="eyebrow">
                        {stop.entity.entity_type} ·{" "}
                        {stop.entity.verification_status.replaceAll("_", " ")}
                      </span>
                      <h3>{stop.entity.canonical_name}</h3>
                      <p>
                        {String(stop.entity.facts.address || "Address unknown")}
                      </p>
                      <p>{stop.explanation}</p>
                      <p className="outing-note">
                        {stop.duration_assumed
                          ? "Visit duration is a planning assumption."
                          : "Provider-sourced event times."}{" "}
                        Booking and inventory availability unknown.
                      </p>
                      {Object.keys(stop.entity.conflicts).length > 0 && (
                        <p className="outing-warning">
                          Conflicting evidence:{" "}
                          {Object.keys(stop.entity.conflicts).join(", ")}.
                          Disputed facts are withheld when sources have equal
                          authority.
                        </p>
                      )}
                      {i > 0 && (
                        <p>
                          {alternative.routes.find(
                            (r) => r.destination_id === stop.entity.entity_id,
                          )
                            ? `${Math.ceil(alternative.routes.find((r) => r.destination_id === stop.entity.entity_id)!.duration_seconds / 60)} min travel estimate · ${result.mode === "demo" ? "fictional route" : "Google Maps"}`
                            : "Travel estimate unavailable"}
                        </p>
                      )}
                      <details>
                        <summary>Illustrative value & conditions</summary>
                        {stop.entity.amex_matches.length === 0 ? (
                          <p>
                            No corroborated merchant offer match for this stop.
                          </p>
                        ) : (
                          stop.entity.amex_matches.map((m) => (
                            <div key={m.source_id}>
                              <strong>
                                {m.title} ·{" "}
                                {m.kind === "REWARD"
                                  ? `${m.points} points`
                                  : m.amount === null ? "Experience benefit; no cash amount" : `${m.currency} ${m.amount}`}
                              </strong>
                              <p>
                                {m.label} ·{" "}
                                {m.included
                                  ? "Included"
                                  : m.eligible
                                    ? "Alternative value — not added to the total"
                                    : "Conditions not confirmed"}
                              </p>
                              {m.conditions.map((condition, j) => (
                                <label
                                  className="outing-condition"
                                  key={m.condition_ids[j]}
                                >
                                  <input
                                    type="checkbox"
                                    checked={conditions.includes(
                                      m.condition_ids[j],
                                    )}
                                    onChange={(e) =>
                                      setConditions((old) =>
                                        e.target.checked
                                          ? [...old, m.condition_ids[j]]
                                          : old.filter(
                                              (v) => v !== m.condition_ids[j],
                                            ),
                                      )
                                    }
                                  />
                                  {condition}
                                </label>
                              ))}
                              <small>
                                Source: {m.source} · Expires{" "}
                                {new Date(m.expires_at).toLocaleString()}.
                                Replan to apply changed conditions.
                              </small>
                            </div>
                          ))
                        )}
                      </details>
                      <Evidence items={stop.entity.sources} />
                    </article>
                  </li>
                ))}
              </ol>
              <p className="outing-note">
                Run available until{" "}
                {new Date(result.expires_at).toLocaleTimeString()}. Replan to
                refresh expired evidence. No reservations or payments are made.
              </p>
            </>
          )}
        </div>
      )}
    </section>
  );
}

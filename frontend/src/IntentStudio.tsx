import { useState } from "react";
import { api } from "./api";
import type { Customer, Detection } from "./types";

const journeys = {
  discovery: {
    title: "Just exploring",
    purpose: "leisure",
    events: ["ad_click"],
  },
  planning: {
    title: "Planning a culture escape",
    purpose: "leisure",
    events: ["ad_click", "travel_search", "hotel_search"],
  },
  booked: {
    title: "A confirmed holiday",
    purpose: "leisure",
    events: ["travel_search", "travel_booking"],
  },
  business: {
    title: "A business stay",
    purpose: "business",
    events: ["customer_declared_intent", "hotel_search"],
  },
  repeated: {
    title: "Repeated clicks",
    purpose: "leisure",
    events: ["ad_click", "ad_click", "ad_click"],
  },
} as const;
type Preset = keyof typeof journeys;
type Step = {
  event: string;
  score: number;
  stage: string;
  contribution: number;
};

export function IntentStudio({
  customer,
  disabled,
  onApply,
  onRunState,
}: {
  customer: Customer;
  disabled: boolean;
  onApply: (ids: string[]) => Promise<void>;
  onRunState: (running: boolean) => void;
}) {
  const [preset, setPreset] = useState<Preset>("planning");
  const [start, setStart] = useState("2026-10-10");
  const [end, setEnd] = useState("2026-10-15");
  const [steps, setSteps] = useState<Step[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  async function replay() {
    setRunning(true);
    onRunState(true);
    setError("");
    setSteps([]);
    try {
      const health = await api<{ clock: string }>("/health");
      const ids: string[] = [];
      for (const event of journeys[preset].events) {
        const id = `sim-${crypto.randomUUID()}`;
        await api("/signals", "POST", {
          event_id: id,
          customer_id: customer.customer_id,
          source: "synthetic_intent_studio",
          event_type: event,
          timestamp: new Date(
            Date.parse(health.clock) -
              (journeys[preset].events.length - ids.length) * 1000,
          ).toISOString(),
          synthetic: true,
          consent: customer.consent,
          context: {
            destination: "Rome",
            start_date: start,
            end_date: end,
            purpose: journeys[preset].purpose,
            preferences: [],
          },
        });
        ids.push(id);
        const result = await api<Detection>("/intents/detect", "POST", {
          customer_id: customer.customer_id,
          signal_ids: ids,
        });
        if (!result.intent)
          throw new Error(result.abstention_reasons.join(" "));
        const intent = result.intent;
        setSteps((previous) => [
          ...previous,
          {
            event,
            score: intent.confidence,
            stage: intent.intent_stage,
            contribution:
              intent.evidence.find((e) => e.source_id === id)?.weight ?? 0,
          },
        ]);
      }
      await onApply(ids);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to replay these events.",
      );
    } finally {
      setRunning(false);
      onRunState(false);
    }
  }
  return (
    <details className="intent-studio">
      <summary>
        Shape your trip{" "}
        <span>Edit dates or replay a synthetic travel journey</span>
      </summary>
      <p>
        Each replay sends events through the actual signal and intent APIs. Your
        saved interests still shape recommendations. Each run uses only its own
        trip signals.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void replay();
        }}
      >
        <label>
          Travel scenario
          <select
            value={preset}
            disabled={running || disabled}
            onChange={(e) => setPreset(e.target.value as Preset)}
          >
            {Object.entries(journeys).map(([key, value]) => (
              <option key={key} value={key}>
                {value.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Departure
          <input
            required
            type="date"
            value={start}
            disabled={running || disabled}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          Return
          <input
            required
            type="date"
            min={start}
            value={end}
            disabled={running || disabled}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
        <button
          className="button"
          disabled={running || disabled || !customer.consent.allowed}
        >
          {running ? "Replaying journey…" : "Build my Rome experience"}
        </button>
      </form>
      {!customer.consent.allowed && (
        <p>Enable personalization in your preferences to replay a journey.</p>
      )}
      <p className="journey-context">
        Synthetic demo · Rome only · Business travel changes trip context;
        catalog applicability still follows explicit rules. Dates outside
        catalog validity may have no matching benefits.
      </p>
      {error && <p role="alert">{error}</p>}
      <ol className="intent-timeline" aria-live="polite">
        {steps.map((step, index) => (
          <li key={index}>
            <strong>{step.event.replaceAll("_", " ")}</strong>
            <span>
              +{step.contribution.toFixed(2)} contribution →{" "}
              {Math.round(step.score * 100)}/100 · {step.stage}
            </span>
          </li>
        ))}
      </ol>
      {steps.length > 0 && (
        <p>
          Intent strength is a documented rules score, not a probability. Each
          event type contributes once per trip; repeated clicks add zero.
          Booking changes the stage to booked.
        </p>
      )}
    </details>
  );
}

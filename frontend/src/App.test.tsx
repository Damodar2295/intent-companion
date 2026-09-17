import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { api } from "./api";
import { ValuePanel } from "./Recommendations";
import type {
  Customer,
  Experience,
  Preference,
  Recommendation,
  Scenario,
} from "./types";

vi.mock("./api", () => ({ api: vi.fn() }));

const scenarios: Scenario[] = [
  {
    scenario_id: "prospect",
    customer_id: "cust-prospect",
    title: "A new chapter",
    subtitle: "Prospect",
    signal_ids: ["evt-prospect"],
  },
  {
    scenario_id: "dining",
    customer_id: "cust-dining",
    title: "A taste of culture",
    subtitle: "Dining",
    signal_ids: ["evt-1"],
  },
  {
    scenario_id: "stay",
    customer_id: "cust-stay",
    title: "A considered escape",
    subtitle: "Shopping",
    signal_ids: ["evt-2"],
  },
];
let customers: Record<string, Customer>;

function experience(id: string): Experience {
  const profile = customers[id];
  const stay = id === "cust-stay";
  const recommendation: Recommendation = {
    recommendation_id: stay ? "rec:card-b" : "rec:card-a",
    recommendation_type: "card",
    title: stay ? "Sanctuary · Demo Card" : "Savor · Demo Card",
    description: "A synthetic concept card.",
    category: stay ? "hotel" : "dining",
    product_ids: [stay ? "card-b" : "card-a"],
    relevance_score: 0.8,
    evidence: [
      {
        evidence_id: "catalog:card-a",
        type: "catalog",
        source_id: "card-a",
        fact: "Verified synthetic catalog fact.",
        weight: null,
      },
    ],
    value: [],
    source_ids: ["card-a"],
    conditions: [],
    explanation: "Matched to active preferences.",
  };
  return {
    experience_id: "test",
    customer_id: id,
    lifecycle_stage: "member",
    intent: null,
    headline: "Rome",
    summary: "Synthetic experience",
    recommended_cards: [recommendation],
    benefits: [],
    offers: [],
    rewards: [],
    merchants: [],
    value_summary: [],
    preferences_used: profile.stated_preferences,
    status: "ready",
    abstention_reasons: [],
    provider_mode: "deterministic",
    fallback_reason: null,
    trace: [],
  };
}

beforeEach(() => {
  window.history.replaceState({}, "", "/app/");
  customers = Object.fromEntries(
    scenarios.map((s) => [
      s.customer_id,
      {
        customer_id: s.customer_id,
        display_name: s.title,
        lifecycle_stage: s.scenario_id === "prospect" ? "prospect" : "member",
        existing_cards:
          s.scenario_id === "prospect" ? [] : ["card-a", "card-b"],
        stated_preferences:
          s.scenario_id === "dining"
            ? ["fine dining", "museums"]
            : ["shopping", "luxury hotels"],
        suppressed_preferences: [],
        consent: { allowed: true, purpose: "personalization" },
      },
    ]),
  ) as Record<string, Customer>;
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(
    async <T,>(path: string, method = "GET", body?: unknown): Promise<T> => {
      const request = body as
        | { customer_id?: string; preference?: Preference; allowed?: boolean }
        | undefined;
      const id = path.split("/")[2];
      let result: unknown;
      if (path === "/scenarios") result = scenarios;
      else if (path === "/intents/detect")
        result = customers[request!.customer_id!].consent.allowed
          ? {
              status: "ready",
              intent: { intent_id: "intent-1" },
              abstention_reasons: [],
            }
          : {
              status: "abstained",
              intent: null,
              abstention_reasons: [
                "Personalization consent is missing or withdrawn.",
              ],
            };
      else if (path === "/companion")
        result = experience(request!.customer_id!);
      else if (path.endsWith("/preferences/remove")) {
        customers[id].stated_preferences = customers[
          id
        ].stated_preferences.filter((p) => p !== request!.preference);
        customers[id].suppressed_preferences.push(request!.preference!);
        result = customers[id];
      } else if (method === "PUT" && path.endsWith("/consent")) {
        customers[id].consent.allowed = request!.allowed!;
        result = customers[id];
      } else result = customers[id];
      return structuredClone(result) as T;
    },
  );
});
afterEach(cleanup);

describe("Companion interactions", () => {
  it("separates prospect exploration from the member wallet", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "Savor" });
    fireEvent.click(screen.getByRole("button", { name: /Prospect Discover/ }));
    await screen.findByRole("button", { name: /Explore Card/ });
    expect(
      screen.queryByRole("button", { name: /A considered escape/ }),
    ).not.toBeInTheDocument();
    expect(window.location.search).toBe("?journey=prospect");
    fireEvent.click(screen.getByRole("button", { name: /Card Member Make/ }));
    await screen.findByRole("heading", {
      name: "Your best companion is already in your wallet.",
    });
    expect(
      screen.queryByRole("button", { name: /Explore Card/ }),
    ).not.toBeInTheDocument();
  });

  it("opens the prospect journey directly from its demo link", async () => {
    window.history.replaceState({}, "", "/app/?journey=prospect");
    render(<App />);
    await screen.findByRole("button", { name: /Explore Card/ });
    expect(
      screen.getByRole("heading", { name: "Find your kind of rewarding." }),
    ).toBeInTheDocument();
  });
  it("loads and switches scenarios without retaining the previous card", async () => {
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: "Savor" }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /A considered escape/ }),
    );
    expect(
      await screen.findByRole("heading", { name: "Sanctuary" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Savor" }),
    ).not.toBeInTheDocument();
  });

  it("removes a preference and regenerates", async () => {
    render(<App />);
    const remove = await screen.findByRole("button", {
      name: "Remove fine dining",
    });
    await waitFor(() => expect(remove).toBeEnabled());
    fireEvent.click(remove);
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Remove fine dining" }),
      ).not.toBeInTheDocument(),
    );
    expect(
      await screen.findByText(/Removed preferences stay suppressed/),
    ).toBeInTheDocument();
    expect(customers["cust-dining"].suppressed_preferences).toContain(
      "fine dining",
    );
  });

  it("withdraws consent and clears personalized recommendations", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "Savor" });
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Allow personalization/ }),
    );
    expect(
      await screen.findByText("Trust comes before a recommendation."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Savor" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Allow personalization/ }),
    );
    expect(
      await screen.findByRole("heading", { name: "Savor" }),
    ).toBeInTheDocument();
  });

  it("shows grounded evidence and labels deterministic mode", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "Savor" });
    fireEvent.click(screen.getByText("Why you’re seeing this"));
    expect(screen.getByText("Verified synthetic catalog fact.")).toBeVisible();
    expect(
      screen.getByText("Deterministic ranking · no model required"),
    ).toBeInTheDocument();
  });

  it("handles initial API failure", async () => {
    vi.mocked(api).mockRejectedValue(new Error("offline"));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Cannot reach the companion API",
    );
  });

  it("shows excluded alternatives without adding them to the total", () => {
    render(
      <ValuePanel
        title="Savor"
        value={{
          product_id: "card-a",
          totals_by_currency: { USD: "40.00" },
          disclaimer: "Synthetic values.",
          breakdown: [
            {
              source_id: "offer-1",
              product_id: "card-a",
              value_type: "savings",
              amount: "30.00",
              currency: "USD",
              calculation_rule: "fixed amount",
              assumptions: [],
              included_in_total: false,
              exclusion_reason:
                "Alternative; only the highest value is counted.",
            },
          ],
        }}
      />,
    );
    fireEvent.click(screen.getByText("See the calculation"));
    expect(screen.getByText(/\$40.00/)).toBeVisible();
    expect(screen.getByText("Not added")).toBeVisible();
  });
});

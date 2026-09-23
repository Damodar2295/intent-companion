import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OutingPlanner } from "./OutingPlanner";
import { api, streamOuting } from "./api";
import type { Customer, OutingEvent } from "./types";

vi.mock("./api", () => ({ api: vi.fn(), streamOuting: vi.fn() }));
const customer: Customer = {
  customer_id: "cust-dining",
  display_name: "Member",
  lifecycle_stage: "member",
  existing_cards: ["card-a"],
  stated_preferences: ["dining"],
  suppressed_preferences: [],
  consent: { allowed: true, purpose: "personalization" },
};
const event: OutingEvent = {
  run_id: "run",
  sequence: 1,
  stage: "PARTIAL",
  timestamp: new Date().toISOString(),
  message: "Completed",
  result: {
    outing_id: "run",
    status: "PARTIAL",
    mode: "realtime",
    warnings: ["Routing unavailable"],
    hypothetical: false,
    search_plan: { timezone: "Europe/Rome" },
    expires_at: new Date(Date.now() + 300000).toISOString(),
    alternatives: [
      {
        feasibility: "INCOMPLETE",
        reward_points: 100,
        totals_by_currency: { USD: "30", EUR: "10" },
        routes: [],
        stops: [
          {
            arrival: "2026-10-02T17:00:00+02:00",
            departure: "2026-10-02T18:00:00+02:00",
            duration_assumed: true,
            explanation: "Selected for your requested activity mix.",
            entity: {
              entity_id: "p",
              canonical_name: "Verified place",
              entity_type: "DINING",
              verification_status: "PARTIALLY_VERIFIED",
              facts: { address: "Rome" },
              conflicts: {},
              sources: [],
              amex_matches: [],
            },
          },
        ],
      },
    ],
  },
};
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
function setup() {
  vi.mocked(api).mockResolvedValue({ mode: "realtime" });
  return render(<OutingPlanner customer={customer} />);
}
describe("Outing journey", () => {
  it("renders partial provider output, currencies and points separately", async () => {
    vi.mocked(streamOuting).mockImplementation(async (_body, _signal, notify) =>
      notify(event),
    );
    setup();
    fireEvent.click(screen.getByText("Plan my outing"));
    expect(await screen.findByText("Verified place")).toBeInTheDocument();
    expect(screen.getByText("Routing unavailable")).toBeInTheDocument();
    expect(screen.getByText("USD 30 · EUR 10")).toBeInTheDocument();
    expect(
      screen.getByText("100 reward points · valued separately"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No corroborated merchant offer match for this stop."),
    ).toBeInTheDocument();
  });
  it("cancels the fetch and leaves no spinner", async () => {
    vi.mocked(streamOuting).mockImplementation(
      (_body, signal) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );
    setup();
    fireEvent.click(screen.getByText("Plan my outing"));
    fireEvent.click(screen.getByText("Cancel"));
    expect(await screen.findByText("Planning cancelled.")).toBeInTheDocument();
    expect(screen.getByText("Plan my outing")).not.toBeDisabled();
  });
  it("clears results after withdrawal or a preference change", async () => {
    vi.mocked(streamOuting).mockImplementation(async (_body, _signal, notify) =>
      notify(event),
    );
    const view = setup();
    fireEvent.click(screen.getByText("Plan my outing"));
    await screen.findByText("Verified place");
    view.rerender(
      <OutingPlanner
        customer={{
          ...customer,
          consent: { allowed: false, purpose: "personalization" },
        }}
      />,
    );
    await waitFor(() =>
      expect(screen.queryByText("Verified place")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Plan my outing")).toBeDisabled();
  });
  it("shows actionable configuration errors", async () => {
    vi.mocked(streamOuting).mockRejectedValue(
      new Error("Configure OPENAI_MODEL"),
    );
    setup();
    fireEvent.click(screen.getByText("Plan my outing"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Configure OPENAI_MODEL",
    );
  });
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { api } from "./api";
import { IntentStudio } from "./IntentStudio";
vi.mock("./api", () => ({ api: vi.fn() }));

it("replays isolated signals and applies only the generated trip", async () => {
  const apply = vi.fn().mockResolvedValue(undefined);
  const state = vi.fn();
  vi.mocked(api).mockImplementation(async (path, _method, body) => {
    if (path === "/health") return { clock: "2026-09-17T12:00:00Z" } as never;
    if (path === "/signals") return { status: "created" } as never;
    const ids = (body as { signal_ids: string[] }).signal_ids;
    return {
      intent: {
        confidence: 0.1,
        intent_stage: "exploring",
        evidence: [
          { source_id: ids.at(-1), weight: ids.length === 1 ? 0.1 : 0 },
        ],
      },
    } as never;
  });
  render(
    <IntentStudio
      customer={{
        customer_id: "test",
        display_name: "Demo",
        lifecycle_stage: "member",
        existing_cards: [],
        stated_preferences: [],
        suppressed_preferences: [],
        consent: { allowed: true, purpose: "personalization" },
      }}
      disabled={false}
      onApply={apply}
      onRunState={state}
    />,
  );
  fireEvent.click(screen.getByText("Shape your trip"));
  fireEvent.change(screen.getByLabelText("Travel scenario"), {
    target: { value: "repeated" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Build my Rome experience" }),
  );
  await waitFor(() => expect(apply).toHaveBeenCalledOnce());
  expect(new Set(apply.mock.calls[0][0]).size).toBe(3);
  expect(screen.getAllByText(/\+0.00 contribution/)).toHaveLength(2);
  expect(state).toHaveBeenLastCalledWith(false);
});

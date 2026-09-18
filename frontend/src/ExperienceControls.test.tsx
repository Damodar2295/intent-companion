import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { IntentControls, SupplementaryExplore } from "./ExperienceControls";
import { api } from "./api";

vi.mock("./api", () => ({ api: vi.fn() }));

describe("explicit customer controls", () => {
  it("never suggests a supplementary action before explicit interest", () => {
    render(<SupplementaryExplore />);
    expect(screen.queryByRole("button", { name: "Explore supplementary card", hidden: true })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Traveling together?"));
    fireEvent.click(screen.getByLabelText("I want to explore shared spending"));
    fireEvent.click(screen.getByRole("button", { name: "Explore supplementary card" }));
    expect(screen.getByRole("status")).toHaveTextContent("No application has been submitted");
  });

  it("persists dismissal with the explicit business owner", async () => {
    vi.mocked(api).mockResolvedValue({ status: "dismissed" });
    const change = vi.fn();
    render(<IntentControls owner="biz-bakery" intent="intent-test" business status="unconfirmed" onChange={change} />);
    fireEvent.click(screen.getByRole("button", { name: "Not relevant" }));
    expect(await screen.findByRole("button", { name: "Restore intent" })).toBeInTheDocument();
    expect(api).toHaveBeenCalledWith("/business/intents/intent-test/feedback", "POST", { owner_id: "biz-bakery", action: "dismiss" });
  });
});

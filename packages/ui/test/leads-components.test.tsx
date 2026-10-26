// The component additions for the lead screens (Phase 4 part 3): the pipeline stage chips and
// per-row classes on Table (unread leads are bold), with their accessibility rules.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Chip, Table, type ChipVariant } from "../src";

afterEach(cleanup);

describe("Chip stage variants", () => {
  it.each<[ChipVariant, string, string]>([
    ["stageNew", "New", "text-stage-new-text"],
    ["stageContacted", "Contacted", "border-stage-contacted-border"],
    ["stageSiteVisit", "Site visit", "text-stage-site-visit-text"],
    ["stageNegotiation", "Negotiation", "bg-stage-negotiation-bg"],
    ["stageBooked", "Booked", "bg-stage-booked-bg"],
    ["stageLost", "Lost", "bg-stage-lost-bg"],
  ])("%s says %s in words and uses the stage tokens", (variant, label, token) => {
    render(<Chip variant={variant}>{label}</Chip>);
    const chip = screen.getByText(label);
    expect(chip.className).toContain(token);
  });
});

describe("Table rowClassName", () => {
  it("adds classes to the rows it names and leaves the others alone", () => {
    const rows = [
      { id: "a", name: "Sample Lead 1", unread: true },
      { id: "b", name: "Sample Lead 2", unread: false },
    ];
    render(
      <Table
        caption="Leads"
        rows={rows}
        rowKey={(row) => row.id}
        rowClassName={(row) => (row.unread ? "font-bold" : undefined)}
        columns={[{ key: "name", header: "Name", rowHeader: true, cell: (row) => row.name }]}
      />,
    );
    const table = screen.getByRole("table", { name: "Leads" });
    const [, first, second] = within(table).getAllByRole("row");
    expect(first?.className).toContain("font-bold");
    expect(second?.className).not.toContain("font-bold");
    // The base rule stays on every row.
    expect(second?.className).toContain("border-t");
  });
});

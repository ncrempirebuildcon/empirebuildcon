// Behaviour and accessibility of the CMS form and list components (handbook/DESIGN_SYSTEM.md §9).
import { useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  Button,
  CharacterCount,
  Chip,
  ConfirmDialog,
  NumberField,
  ReorderButtons,
  ReorderList,
  Select,
  Table,
  TabPanel,
  Tabs,
  Textarea,
  moveAnnouncement,
  moveItem,
  parseNumberInput,
} from "../src";

afterEach(cleanup);

describe("Select", () => {
  it("is labelled, lists the options and links its error", () => {
    render(
      <Select
        label="City"
        placeholder="Choose a city"
        options={[
          { value: "a", label: "Sample City" },
          { value: "b", label: "Other City" },
        ]}
        error="Choose a city."
        defaultValue=""
      />,
    );
    const select = screen.getByLabelText("City") as HTMLSelectElement;
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Choose a city", "Sample City", "Other City"]);
    expect(select.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("Choose a city.").id).toBe(select.getAttribute("aria-describedby"));
  });
});

describe("Textarea and CharacterCount", () => {
  it("links the hint to the textarea", () => {
    render(<Textarea label="Short description" hint="Formatting: *bold*" />);
    const box = screen.getByLabelText("Short description");
    expect(box.tagName).toBe("TEXTAREA");
    expect(screen.getByText("Formatting: *bold*").id).toBe(box.getAttribute("aria-describedby"));
  });

  it("says when text is over the recommended length, in words", () => {
    const { rerender } = render(<CharacterCount value="Hello" limit={60} />);
    expect(screen.getByText("5 / 60 characters · good")).toBeTruthy();
    rerender(<CharacterCount value={"x".repeat(61)} limit={60} />);
    expect(screen.getByText("61 / 60 characters · too long")).toBeTruthy();
    rerender(<CharacterCount value="" limit={60} />);
    expect(screen.getByText("0 / 60 characters")).toBeTruthy();
  });
});

describe("NumberField", () => {
  it.each([
    ["", 0, false, null],
    ["78,00,000", 0, false, 7_800_000],
    ["7800000", 0, false, 7_800_000],
    ["12.5", 0, false, undefined],
    ["12.5", 1, false, 12.5],
    ["28.61391", 6, false, 28.61391],
    ["-", 6, true, undefined],
    ["-77.2", 6, true, -77.2],
    ["-77.2", 6, false, undefined],
    ["abc", 0, false, undefined],
  ])("parses %j (decimals %d, negative %s) as %s", (text, decimals, negative, expected) => {
    expect(parseNumberInput(text, decimals, negative)).toBe(expected);
  });

  function Harness({ onValue }: { onValue: (v: number | null) => void }) {
    const [value, setValue] = useState<number | null>(7_800_000);
    return (
      <NumberField
        label="Price from (₹)"
        value={value}
        onValueChange={(v) => {
          setValue(v);
          onValue(v);
        }}
      />
    );
  }

  it("shows Indian grouping when idle and reports whole rupees", () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);
    const input = screen.getByLabelText("Price from (₹)") as HTMLInputElement;
    expect(input.value).toBe("78,00,000");
    expect(input.getAttribute("inputmode")).toBe("numeric");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "12500000" } });
    expect(onValue).toHaveBeenLastCalledWith(12_500_000);
    expect(input.value).toBe("12500000");
    fireEvent.blur(input);
    expect(input.value).toBe("1,25,00,000");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "" } });
    expect(onValue).toHaveBeenLastCalledWith(null);
  });

  it("ignores text that is not a number yet", () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);
    const input = screen.getByLabelText("Price from (₹)") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "12a" } });
    expect(onValue).not.toHaveBeenCalled();
    fireEvent.blur(input);
    expect(input.value).toBe("78,00,000");
  });
});

describe("Tabs", () => {
  function Harness() {
    const [selected, setSelected] = useState("details");
    const tabs = [
      { id: "details", label: "Details" },
      { id: "configurations", label: "Configurations" },
      { id: "seo", label: "SEO" },
    ];
    return (
      <>
        <Tabs
          label="Project sections"
          idPrefix="t"
          tabs={tabs}
          selected={selected}
          onSelect={setSelected}
        />
        {tabs.map((tab) => (
          <TabPanel key={tab.id} idPrefix="t" tabId={tab.id} selected={tab.id === selected}>
            {tab.label} panel
          </TabPanel>
        ))}
      </>
    );
  }

  it("marks the selected tab and links tabs to panels", () => {
    render(<Harness />);
    const tab = screen.getByRole("tab", { name: "Details" });
    expect(tab.getAttribute("aria-selected")).toBe("true");
    expect(tab.tabIndex).toBe(0);
    expect(screen.getByRole("tab", { name: "SEO" }).tabIndex).toBe(-1);
    const panel = screen.getByRole("tabpanel", { name: "Details" });
    expect(tab.getAttribute("aria-controls")).toBe(panel.id);
  });

  it("moves with the arrow keys, Home and End, wrapping at the ends", () => {
    render(<Harness />);
    const details = screen.getByRole("tab", { name: "Details" });
    fireEvent.keyDown(details, { key: "ArrowLeft" });
    const seo = screen.getByRole("tab", { name: "SEO" });
    expect(seo.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(seo);
    fireEvent.keyDown(seo, { key: "ArrowRight" });
    expect(document.activeElement).toBe(details);
    fireEvent.keyDown(details, { key: "End" });
    expect(document.activeElement).toBe(seo);
    fireEvent.keyDown(seo, { key: "Home" });
    expect(screen.getByRole("tabpanel", { name: "Details" })).toBeTruthy();
  });
});

describe("Table", () => {
  it("has a caption, column headers and row headers", () => {
    render(
      <Table
        caption="Projects"
        captionHidden
        rows={[{ id: "1", name: "Sample — Project A", city: "Sample City" }]}
        rowKey={(r) => r.id}
        columns={[
          { key: "name", header: "Name", rowHeader: true, cell: (r) => r.name },
          { key: "city", header: "City", cell: (r) => r.city },
          { key: "actions", header: "Actions", headerHidden: true, cell: () => "Edit" },
        ]}
      />,
    );
    const table = screen.getByRole("table", { name: "Projects" });
    expect(within(table).getAllByRole("columnheader")).toHaveLength(3);
    expect(within(table).getByRole("rowheader").textContent).toBe("Sample — Project A");
    const region = screen.getByRole("region", { name: "Projects" });
    expect(region.tabIndex).toBe(0);
    // Positioned, so screen-reader-only headers stay inside the scroll area (no page scroll).
    expect(region.className).toContain("relative");
    expect(region.className).toContain("overflow-x-auto");
  });

  it("shows the empty message when there are no rows", () => {
    render(
      <Table
        caption="Projects"
        rows={[] as Array<{ id: string }>}
        rowKey={(r) => r.id}
        columns={[{ key: "id", header: "Id", cell: (r) => r.id }]}
        empty="No projects yet."
      />,
    );
    expect(screen.getByText("No projects yet.")).toBeTruthy();
  });
});

describe("ConfirmDialog", () => {
  it("is a labelled dialog that focuses Cancel first", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Delete this draft?"
        confirmLabel="Delete project"
        tone="danger"
        onConfirm={onConfirm}
        onCancel={onCancel}
      >
        It can&apos;t be undone.
      </ConfirmDialog>,
    );
    const dialog = screen.getByRole("dialog", { name: "Delete this draft?" });
    expect(dialog.getAttribute("aria-describedby")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete project" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("ignores Escape and clicks while busy", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        busy
        title="Archive this project?"
        confirmLabel="Archive project"
        onConfirm={onConfirm}
        onCancel={onCancel}
      >
        Archiving removes the project from the website.
      </ConfirmDialog>,
    );
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    fireEvent.click(screen.getByRole("button", { name: "Archive project" }));
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("renders nothing inside while closed", () => {
    render(
      <ConfirmDialog
        open={false}
        title="Hidden"
        confirmLabel="Go"
        onConfirm={() => {}}
        onCancel={() => {}}
      >
        Body
      </ConfirmDialog>,
    );
    expect(screen.queryByText("Body")).toBeNull();
  });
});

describe("Reorder", () => {
  it("moves one item and leaves the input untouched", () => {
    const input = ["A", "B", "C"];
    expect(moveItem(input, 2, 0)).toEqual(["C", "A", "B"]);
    expect(moveItem(input, 0, 1)).toEqual(["B", "A", "C"]);
    expect(moveItem(input, 0, -1)).toEqual(["A", "B", "C"]);
    expect(input).toEqual(["A", "B", "C"]);
    expect(moveAnnouncement("Tower B", 0, 3)).toBe("Tower B moved to position 1 of 3.");
  });

  it("disables Move up on the first item without removing it from the tab order", () => {
    const onMove = vi.fn();
    render(<ReorderButtons index={0} count={2} itemLabel="Tower A" onMove={onMove} />);
    const up = screen.getByRole("button", { name: "Move Tower A up" });
    expect(up.getAttribute("aria-disabled")).toBe("true");
    expect(up.hasAttribute("disabled")).toBe(false);
    fireEvent.click(up);
    expect(onMove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Move Tower A down" }));
    expect(onMove).toHaveBeenCalledWith(0, 1);
  });

  it("reorders a list and announces the new position", () => {
    function Harness() {
      const [items, setItems] = useState(["Tower A", "Tower B", "Tower C"]);
      return (
        <ReorderList
          label="Towers in display order"
          items={items}
          getKey={(i) => i}
          getLabel={(i) => i}
          onReorder={setItems}
          renderItem={(i) => <span>{i}</span>}
        />
      );
    }
    render(<Harness />);
    const up = screen.getByRole("button", { name: "Move Tower C up" });
    up.focus();
    fireEvent.click(up);
    const list = screen.getByRole("list", { name: "Towers in display order" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["Tower A", "Tower C", "Tower B"]);
    expect(screen.getByRole("status").textContent).toBe("Tower C moved to position 2 of 3.");
    // The focused button travels with its item (rows are keyed by id, not position).
    expect(document.activeElement).toBe(up);
    expect(up.isConnected).toBe(true);
  });

  it("hides the move buttons for read-only users", () => {
    render(
      <ReorderList
        label="Towers"
        readOnly
        items={["Tower A", "Tower B"]}
        getKey={(i) => i}
        getLabel={(i) => i}
        onReorder={() => {}}
        renderItem={(i) => i}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("New variants", () => {
  it("danger buttons and status chips keep text labels", () => {
    render(
      <>
        <Button variant="danger">Archive project</Button>
        <Chip variant="available">Available</Chip>
        <Chip variant="offMarket">Off market</Chip>
        <Chip variant="upcoming">Upcoming</Chip>
      </>,
    );
    expect(screen.getByRole("button", { name: "Archive project" }).className).toContain(
      "border-danger",
    );
    expect(screen.getByText("Off market")).toBeTruthy();
  });
});

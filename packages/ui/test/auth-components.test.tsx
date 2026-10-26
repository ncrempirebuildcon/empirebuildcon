// Behaviour and accessibility of the sign-in and settings pieces (Phase 4 part 5): the password
// field's show/hide button, the one-time code field, the recovery-code list and vertical tabs
// (handbook/DESIGN_SYSTEM.md §9, SECURITY.md §1).
import { useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  CodeList,
  OneTimeCodeField,
  PasswordField,
  TabPanel,
  Tabs,
  codeDigits,
  spellCode,
} from "../src";

afterEach(cleanup);

describe("PasswordField", () => {
  it("is labelled, hidden by default and toggled by a pressed button that never submits", () => {
    let submitted = 0;
    render(
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submitted += 1;
        }}
      >
        <PasswordField label="New password" autoComplete="new-password" toggleNoun="new password" />
      </form>,
    );
    const input = screen.getByLabelText("New password") as HTMLInputElement;
    expect(input.type).toBe("password");
    expect(input.getAttribute("autocomplete")).toBe("new-password");
    expect(input.getAttribute("autocapitalize")).toBe("none");
    expect(input.getAttribute("spellcheck")).toBe("false");

    const toggle = screen.getByRole("button", { name: "Show new password" });
    expect(toggle.getAttribute("type")).toBe("button");
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(toggle);
    expect(input.type).toBe("text");
    const hide = screen.getByRole("button", { name: "Hide new password" });
    expect(hide.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(hide);
    expect(input.type).toBe("password");
    expect(submitted).toBe(0);
  });

  it("links the API's policy message to the field", () => {
    render(
      <PasswordField
        label="New password"
        autoComplete="new-password"
        hint="12 characters or more."
        error="This password is too common. Try a short sentence you will remember."
      />,
    );
    const input = screen.getByLabelText("New password");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const describedBy = (input.getAttribute("aria-describedby") ?? "").split(" ");
    expect(describedBy).toHaveLength(2);
    expect(screen.getByText(/too common/).id).toBe(describedBy[1]);
  });
});

describe("OneTimeCodeField", () => {
  it.each([
    ["123456", "123456"],
    ["123 456", "123456"],
    ["12-34-56", "123456"],
    ["1234567", "123456"],
    ["abc", ""],
    ["０１２", ""],
  ])("keeps only the digits of %j", (typed, expected) => {
    expect(codeDigits(typed)).toBe(expected);
  });

  it("asks for a numeric keypad and the phone's one-time-code autofill", () => {
    function Harness() {
      const [code, setCode] = useState("");
      return <OneTimeCodeField label="6-digit code" value={code} onValueChange={setCode} />;
    }
    render(<Harness />);
    const input = screen.getByLabelText("6-digit code") as HTMLInputElement;
    expect(input.type).toBe("text");
    expect(input.getAttribute("inputmode")).toBe("numeric");
    expect(input.getAttribute("autocomplete")).toBe("one-time-code");
    expect(input.getAttribute("pattern")).toBe("[0-9]{6}");
    // A pasted code with a space is kept whole, not cut at six characters.
    fireEvent.change(input, { target: { value: "123 456" } });
    expect(input.value).toBe("123456");
    fireEvent.change(input, { target: { value: "98a7" } });
    expect(input.value).toBe("987");
  });
});

describe("CodeList", () => {
  it("spells each code for screen readers, in groups", () => {
    expect(spellCode("k7fq-2mzp")).toBe("k 7 f q, 2 m z p");
    expect(spellCode("ABCD EFGH")).toBe("A B C D, E F G H");
    expect(spellCode("abc")).toBe("a b c");
  });

  it("is a named, numbered list whose visible codes are hidden from screen readers", () => {
    render(<CodeList label="Recovery codes" codes={["k7fq-2mzp", "aaaa-bbbb"]} />);
    const list = screen.getByRole("list", { name: "Recovery codes" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    const visible = within(items[0] as HTMLElement).getByText("k7fq-2mzp");
    expect(visible.getAttribute("aria-hidden")).toBe("true");
    const spelled = within(items[0] as HTMLElement).getByText("k 7 f q, 2 m z p");
    expect(spelled.className).toContain("sr-only");
    expect(spelled.className).toContain("select-none");
  });
});

describe("Tabs (vertical)", () => {
  function Harness() {
    const [selected, setSelected] = useState("company");
    const tabs = [
      { id: "company", label: "Company" },
      { id: "contacts", label: "Contacts" },
      { id: "flags", label: "Feature flags" },
    ];
    return (
      <>
        <Tabs
          label="Settings sections"
          tabs={tabs}
          selected={selected}
          onSelect={setSelected}
          idPrefix="settings"
          orientation="vertical"
        />
        {tabs.map((tab) => (
          <TabPanel key={tab.id} idPrefix="settings" tabId={tab.id} selected={tab.id === selected}>
            {tab.label} panel
          </TabPanel>
        ))}
      </>
    );
  }

  it("says it is vertical and moves with Arrow Up and Down, wrapping at the ends", () => {
    render(<Harness />);
    const list = screen.getByRole("tablist", { name: "Settings sections" });
    expect(list.getAttribute("aria-orientation")).toBe("vertical");
    const company = screen.getByRole("tab", { name: "Company" });
    fireEvent.keyDown(company, { key: "ArrowDown" });
    expect(screen.getByRole("tab", { name: "Contacts" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Contacts" }));
    // Left/Right do nothing in a vertical list.
    fireEvent.keyDown(screen.getByRole("tab", { name: "Contacts" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Contacts" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    fireEvent.keyDown(screen.getByRole("tab", { name: "Contacts" }), { key: "ArrowUp" });
    fireEvent.keyDown(screen.getByRole("tab", { name: "Company" }), { key: "ArrowUp" });
    expect(screen.getByRole("tab", { name: "Feature flags" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(screen.getByRole("tabpanel", { name: "Feature flags" }).textContent).toBe(
      "Feature flags panel",
    );
  });

  it("keeps the horizontal keys when no orientation is given", () => {
    render(
      <Tabs
        label="Sections"
        tabs={[
          { id: "a", label: "A" },
          { id: "b", label: "B" },
        ]}
        selected="a"
        onSelect={() => undefined}
        idPrefix="h"
      />,
    );
    expect(screen.getByRole("tablist").getAttribute("aria-orientation")).toBeNull();
  });
});

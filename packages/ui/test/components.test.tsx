// Accessibility attributes of the shared components (handbook/DESIGN_SYSTEM.md §9).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Alert, Button, Checkbox, Chip, TextField } from "../src";

afterEach(cleanup);

describe("Button", () => {
  it("keeps the label and blocks clicks while loading", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Sign in
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Sign in" });
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(button.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("stays focusable when disabled", () => {
    render(<Button disabled>Publish</Button>);
    const button = screen.getByRole("button", { name: "Publish" });
    expect(button.hasAttribute("disabled")).toBe(false);
    expect(button.getAttribute("aria-disabled")).toBe("true");
  });
});

describe("TextField", () => {
  it("links the label, hint and error to the input", () => {
    render(<TextField label="Email" hint="Your work email" error="Enter an email" />);
    const input = screen.getByLabelText("Email");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const describedBy = input.getAttribute("aria-describedby") ?? "";
    expect(describedBy.split(" ")).toHaveLength(2);
    expect(screen.getByText("Enter an email").id).toBe(describedBy.split(" ")[1]);
  });
});

describe("Checkbox", () => {
  it("is never ticked by default (consent rule)", () => {
    render(<Checkbox label="Contact me about this enquiry" required />);
    const box = screen.getByRole("checkbox") as HTMLInputElement;
    expect(box.checked).toBe(false);
    expect(screen.getByText(/\(Required\)/)).toBeTruthy();
  });

  it("links its hint and error, and keeps a caller's own description", () => {
    render(
      <>
        <p id="outside">Why it is locked</p>
        <Checkbox
          label="Show on the website"
          hint="Locked until the consent date is filled in."
          error="Record the consent date first."
          aria-describedby="outside"
        />
      </>,
    );
    const box = screen.getByRole("checkbox", { name: "Show on the website" });
    const described = (box.getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent);
    expect(described).toEqual([
      "Why it is locked",
      "Locked until the consent date is filled in.",
      "Record the consent date first.",
    ]);
    expect(box.getAttribute("aria-invalid")).toBe("true");
  });
});

describe("Chip and Alert", () => {
  it("chips always carry text", () => {
    render(<Chip variant="soldOut">Sold out</Chip>);
    expect(screen.getByText("Sold out")).toBeTruthy();
  });

  it("errors are announced as alerts, other messages as status", () => {
    render(
      <>
        <Alert tone="error">Couldn&apos;t sign in</Alert>
        <Alert tone="success">Saved</Alert>
      </>,
    );
    expect(screen.getByRole("alert").textContent).toContain("sign in");
    expect(screen.getByRole("status").textContent).toContain("Saved");
  });
});

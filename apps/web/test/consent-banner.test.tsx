// @vitest-environment jsdom
/**
 * Component tests for ConsentBanner and CookieSettingsButton (Phase 6 Task 6.1, Scope 2).
 *
 * Verifies:
 * - hidden when enabled is false
 * - hidden when a valid choice is stored
 * - shown when there is none
 * - Accept all stores true/true
 * - Reject all stores false/false
 * - Choose shows both switches off, and Save stores exactly what is switched
 * - openConsentSettings() re-opens it on the Choose view with the stored values, and focus is on its heading
 * - Accept and Reject buttons have the exact same classes
 * - All wording in CONSENT_COPY starts with [DRAFT]
 * - Region has role="region" and aria-label="Cookie choices"
 * - Focus returns to opener after close
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import React from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ConsentBanner, CONSENT_COPY } from "../src/components/consent/ConsentBanner";
import { CookieSettingsButton } from "../src/components/consent/CookieSettingsButton";
import { readConsent, resetConsentMemory, writeConsent } from "../src/lib/consent";

describe("ConsentBanner component (Task 6.1 Scope 2)", () => {
  beforeEach(() => {
    resetConsentMemory();
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    resetConsentMemory();
    window.localStorage.clear();
  });

  it("all strings in CONSENT_COPY start with [DRAFT]", () => {
    Object.entries(CONSENT_COPY).forEach(([key, val]) => {
      if (typeof val === "string") {
        expect(val.startsWith("[DRAFT]"), `${key} must start with [DRAFT]`).toBe(true);
      }
    });
  });

  it("is hidden when enabled is false", () => {
    const { container } = render(<ConsentBanner enabled={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("is hidden when a valid choice is already stored", () => {
    writeConsent({ analytics: true, marketing: false });
    const { container } = render(<ConsentBanner enabled={true} />);
    expect(container.firstChild).toBeNull();
  });

  it("is shown when enabled is true and no choice is stored", () => {
    render(<ConsentBanner enabled={true} />);
    const region = screen.getByRole("region", { name: "Cookie choices" });
    expect(region).toBeDefined();

    const heading = screen.getByRole("heading", { name: CONSENT_COPY.heading });
    expect(heading).toBeDefined();

    expect(screen.getByRole("button", { name: CONSENT_COPY.acceptAll })).toBeDefined();
    expect(screen.getByRole("button", { name: CONSENT_COPY.rejectAll })).toBeDefined();
    expect(screen.getByRole("button", { name: CONSENT_COPY.choose })).toBeDefined();
    const privacyLink = screen.getByRole("link", { name: CONSENT_COPY.privacyLink });
    expect(privacyLink.getAttribute("href")).toBe("/privacy");
  });

  it("Accept and Reject buttons have identical classes and same size", () => {
    render(<ConsentBanner enabled={true} />);
    const acceptBtn = screen.getByRole("button", { name: CONSENT_COPY.acceptAll });
    const rejectBtn = screen.getByRole("button", { name: CONSENT_COPY.rejectAll });

    expect(acceptBtn.className).toBe(rejectBtn.className);
  });

  it("Accept all stores analytics=true and marketing=true then hides banner", () => {
    render(<ConsentBanner enabled={true} />);
    const acceptBtn = screen.getByRole("button", { name: CONSENT_COPY.acceptAll });

    act(() => {
      fireEvent.click(acceptBtn);
    });

    const stored = readConsent();
    expect(stored).not.toBeNull();
    expect(stored?.analytics).toBe(true);
    expect(stored?.marketing).toBe(true);

    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
  });

  it("Reject all stores analytics=false and marketing=false then hides banner", () => {
    render(<ConsentBanner enabled={true} />);
    const rejectBtn = screen.getByRole("button", { name: CONSENT_COPY.rejectAll });

    act(() => {
      fireEvent.click(rejectBtn);
    });

    const stored = readConsent();
    expect(stored).not.toBeNull();
    expect(stored?.analytics).toBe(false);
    expect(stored?.marketing).toBe(false);

    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
  });

  it("Choose shows switches defaulting to off, and Save stores chosen values", () => {
    render(<ConsentBanner enabled={true} />);
    const chooseBtn = screen.getByRole("button", { name: CONSENT_COPY.choose });

    act(() => {
      fireEvent.click(chooseBtn);
    });

    // Necessary switch is on and disabled
    const necessarySwitch = screen.getByRole("switch", { name: /necessary/i });
    expect(necessarySwitch.getAttribute("aria-checked")).toBe("true");
    expect(necessarySwitch.getAttribute("aria-disabled")).toBe("true");

    // Analytics and Marketing switches are off by default
    const analyticsSwitch = screen.getByRole("switch", { name: /analytics/i });
    const marketingSwitch = screen.getByRole("switch", { name: /marketing/i });

    expect(analyticsSwitch.getAttribute("aria-checked")).toBe("false");
    expect(marketingSwitch.getAttribute("aria-checked")).toBe("false");

    // Turn analytics on
    act(() => {
      fireEvent.click(analyticsSwitch);
    });
    expect(analyticsSwitch.getAttribute("aria-checked")).toBe("true");

    // Save choices
    const saveBtn = screen.getByRole("button", { name: CONSENT_COPY.save });
    act(() => {
      fireEvent.click(saveBtn);
    });

    const stored = readConsent();
    expect(stored?.analytics).toBe(true);
    expect(stored?.marketing).toBe(false);
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
  });

  it("openConsentSettings() re-opens in Choose view with stored values and moves focus to heading", () => {
    writeConsent({ analytics: false, marketing: true });

    render(
      <div>
        <CookieSettingsButton />
        <ConsentBanner enabled={true} />
      </div>,
    );

    // Initially hidden because consent is already stored
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();

    const cookieSettingsBtn = screen.getByRole("button", { name: "Cookie settings" });
    cookieSettingsBtn.focus();
    expect(document.activeElement).toBe(cookieSettingsBtn);

    act(() => {
      fireEvent.click(cookieSettingsBtn);
    });

    // Region is now open
    const region = screen.getByRole("region", { name: "Cookie choices" });
    expect(region).toBeDefined();

    // Focus moved to the heading
    const heading = screen.getByRole("heading", { name: CONSENT_COPY.heading });
    expect(document.activeElement).toBe(heading);

    // Switches show the stored values: analytics=false, marketing=true
    const analyticsSwitch = screen.getByRole("switch", { name: /analytics/i });
    const marketingSwitch = screen.getByRole("switch", { name: /marketing/i });

    expect(analyticsSwitch.getAttribute("aria-checked")).toBe("false");
    expect(marketingSwitch.getAttribute("aria-checked")).toBe("true");

    // Click Save choices to dismiss and verify focus returns to Cookie settings button
    const saveBtn = screen.getByRole("button", { name: CONSENT_COPY.save });
    act(() => {
      fireEvent.click(saveBtn);
    });

    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
    expect(document.activeElement).toBe(cookieSettingsBtn);
  });
});

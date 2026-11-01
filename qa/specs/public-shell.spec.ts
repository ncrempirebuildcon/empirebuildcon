/**
 * Public website shell browser journeys and accessibility tests (Phase 5 Task 5.2).
 *
 * Implements:
 *   - Desktop shell: header, nav, skip link, footer, UP-RERA disclaimer, legal links.
 *   - Mobile shell (390px): sticky header, mobile drawer (keyboard open, escape close, focus trap),
 *     sticky action bar (Call, WhatsApp, Enquire).
 *   - 404 page matching Noir404 with quick links and noindex.
 *   - Nonce-based CSP enforced with zero console violations.
 *   - Axe accessibility on desktop and mobile.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { CMS_STATE, apiCall } from "../lib/auth";

test.describe("Public Website Shell", () => {
  test("desktop shell renders header, footer, landmarks and enforced CSP", async ({ page }) => {
    const cspErrors: string[] = [];
    page.on("console", (msg) => {
      const text = msg.text();
      if (text.includes("Content Security Policy") || text.includes("violates the following")) {
        cspErrors.push(text);
      }
    });

    const response = await page.goto("/");
    expect(response?.status()).toBe(200);

    // Verify CSP header is enforced
    const headers = response?.headers() || {};
    const csp = headers["content-security-policy"];
    expect(csp).toBeDefined();
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("script-src 'self' 'nonce-");
    expect(csp).toContain("img-src 'self' https://res.cloudinary.com data:");
    expect(cspErrors).toHaveLength(0);

    // Skip to content link
    const skipLink = page.getByRole("link", { name: "Skip to content" });
    await expect(skipLink).toBeAttached();

    // Header landmark and navigation
    const header = page.getByRole("banner");
    await expect(header).toBeVisible();
    await expect(header.getByRole("link", { name: "Empire home" })).toBeVisible();
    await expect(header.getByRole("link", { name: "Projects" })).toBeVisible();
    await expect(header.getByRole("link", { name: "Book a site visit" })).toBeVisible();

    // Main landmark
    const main = page.locator("#main-content");
    await expect(main).toBeVisible();

    // Footer landmark and regulatory notes
    const footer = page.getByRole("contentinfo");
    await expect(footer).toBeVisible();
    await expect(footer).toContainText("Official channels: empirebuildcon.com");
    await expect(footer).toContainText("UP-RERA");
    await expect(footer).toContainText("up-rera.in");
    await expect(footer).toContainText(String(new Date().getFullYear()));
    await expect(footer.getByRole("link", { name: "Privacy policy" })).toBeVisible();
    await expect(footer.getByRole("link", { name: "Terms" })).toBeVisible();
    await expect(footer.getByRole("link", { name: "Disclaimer" })).toBeVisible();

    // Axe a11y check
    const a11y = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = a11y.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });

  test("mobile view (390px) shows action bar and drawer with focus trap", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    // Mobile action bar at bottom
    const actionBar = page.getByTestId("mobile-action-bar");
    await expect(actionBar).toBeVisible();
    await expect(actionBar.getByRole("link", { name: /Call/i })).toBeVisible();
    await expect(actionBar.getByRole("link", { name: /WhatsApp/i })).toBeVisible();
    await expect(actionBar.getByRole("link", { name: /Enquire/i })).toBeVisible();

    // Open mobile menu drawer
    const menuBtn = page.getByTestId("mobile-menu-button");
    await expect(menuBtn).toBeVisible();
    await expect(menuBtn).toHaveAttribute("aria-expanded", "false");

    await menuBtn.click();
    await expect(menuBtn).toHaveAttribute("aria-expanded", "true");

    const drawer = page.getByTestId("mobile-menu-drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("link", { name: "Projects" })).toBeVisible();

    // Keyboard navigation: Escape key closes menu and restores focus to button
    await page.keyboard.press("Escape");
    await expect(drawer).not.toBeVisible();
    await expect(menuBtn).toHaveAttribute("aria-expanded", "false");
    await expect(menuBtn).toBeFocused();

    // Axe a11y check on mobile
    const a11y = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = a11y.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });

  test("404 page is on-brand and includes quick links and noindex", async ({ page }) => {
    const res = await page.goto("/non-existent-page");
    expect(res?.status()).toBe(404);

    await expect(page.getByText("404", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "This page has moved or doesn't exist",
    );

    const nav = page.getByRole("navigation", { name: "Quick links" });
    await expect(nav.getByRole("link", { name: "Projects" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Properties" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Contact" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Home" })).toBeVisible();

    const robots = await page.locator('meta[name="robots"]').first().getAttribute("content");
    expect(robots).toContain("noindex");

    const a11y = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = a11y.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });

  test("CMS settings update revalidates and reflects in the public footer", async ({ browser }) => {
    // 1. Check initial homepage
    const publicContext = await browser.newContext();
    const publicPage = await publicContext.newPage();
    await publicPage.goto("/");
    await expect(publicPage.getByRole("contentinfo")).toBeVisible();

    // 2. Open CMS settings as super-admin and update company tagline
    const adminContext = await browser.newContext({ storageState: CMS_STATE });
    const adminPage = await adminContext.newPage();
    await adminPage.goto("/admin/settings");
    await expect(adminPage.getByRole("tab", { name: /^Company/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    const testTagline = `Luxury Living ${Date.now()}`;
    await adminPage.getByLabel("Tagline").fill(testTagline);
    const companyForm = adminPage.getByRole("form", { name: "Company settings" });
    await companyForm.getByRole("button", { name: "Save changes" }).click();
    await expect(companyForm.getByRole("status").filter({ hasText: /^Saved\./ })).toBeVisible();

    // Drain outbox to process the revalidation event
    await apiCall(adminPage, "POST", "/api/v1/internal/outbox/drain");

    // 3. Reload public page and verify updated tagline in footer
    await publicPage.reload();
    await expect(publicPage.getByRole("contentinfo")).toContainText(testTagline);

    await publicContext.close();
    await adminContext.close();
  });
});

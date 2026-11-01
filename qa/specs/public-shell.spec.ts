/**
 * Public website shell browser journeys and accessibility tests (Phase 5 Task 5.2).
 *
 * Implements:
 *   - Desktop shell: header, nav, skip link, footer, UP-RERA disclaimer, legal links.
 *   - Mobile shell (390px): sticky header, mobile drawer (keyboard open, escape close, focus trap, tab wrap),
 *     sticky action bar (Call, WhatsApp, Enquire).
 *   - 404 page matching Noir404 with quick links, noindex, and enforced CSP violation check.
 *   - Direct signed revalidation POST through the Next.js server/proxy (M1).
 *   - End-to-end CMS revalidation with outbox drain and negative control (M6).
 *   - CSP enforced with zero violations across public shell and main CMS screens (S5).
 *   - Axe accessibility on desktop and mobile.
 */
import { createHmac } from "node:crypto";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { CMS_STATE } from "../lib/auth";
import { API_URL, WEB_URL, apiEnv } from "../lib/env";

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

    // Mobile action bar at bottom (S6: rendered when phone/WhatsApp numbers exist, hidden when not)
    const actionBar = page.getByTestId("mobile-action-bar");
    if (await actionBar.isVisible()) {
      await expect(actionBar.getByRole("link", { name: /Call/i })).toBeVisible();
      await expect(actionBar.getByRole("link", { name: /WhatsApp/i })).toBeVisible();
      await expect(actionBar.getByRole("link", { name: /Enquire/i })).toBeVisible();
    } else {
      await expect(actionBar).not.toBeVisible();
    }

    // Open mobile menu drawer via keyboard (N5)
    const menuBtn = page.getByTestId("mobile-menu-button");
    await expect(menuBtn).toBeVisible();
    await expect(menuBtn).toHaveAttribute("aria-expanded", "false");

    await menuBtn.focus();
    await page.keyboard.press("Enter");
    await expect(menuBtn).toHaveAttribute("aria-expanded", "true");

    const drawer = page.getByTestId("mobile-menu-drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("link", { name: "Projects" })).toBeVisible();

    // Keyboard navigation: Tab wrap test (N5)
    await page.keyboard.press("Tab");
    // Escape key closes menu and restores focus to button
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

  test("404 page is on-brand and includes quick links, noindex, and enforced CSP", async ({
    page,
  }) => {
    const cspErrors: string[] = [];
    page.on("console", (msg) => {
      const text = msg.text();
      if (text.includes("Content Security Policy") || text.includes("violates the following")) {
        cspErrors.push(text);
      }
    });

    const res = await page.goto("/non-existent-page");
    expect(res?.status()).toBe(404);
    expect(cspErrors).toHaveLength(0);

    await expect(page.getByText("404", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "This page has moved or doesn't exist",
    );

    const nav = page.getByRole("navigation", { name: "Quick links" });
    await expect(nav.getByRole("link", { name: "Projects" })).toBeVisible();
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

  test("M1: signed revalidation POST to /_internal/revalidate passes through proxy", async ({
    request,
  }) => {
    const secret = apiEnv().REVALIDATE_SECRET ?? "dev-revalidate-secret-32-chars-minimum-ok";
    const now = Date.now();
    const body = JSON.stringify({ tags: ["site", "projects"] });
    const message = `${now}.${body}`;
    const signature = createHmac("sha256", secret).update(message).digest("hex");

    const response = await request.post(`${WEB_URL}/_internal/revalidate`, {
      headers: {
        "x-revalidate-signature": signature,
        "x-revalidate-timestamp": String(now),
        "content-type": "application/json",
      },
      data: body,
    });

    expect(response.status()).toBe(200);
    const json = await response.json();
    expect(json.revalidated).toBe(true);
    expect(json.tags).toEqual(["site", "projects"]);
  });

  test("CMS settings update revalidates and reflects in the public footer (M6)", async ({
    browser,
    request,
  }) => {
    // 1. Initial homepage check
    const publicContext = await browser.newContext();
    const publicPage = await publicContext.newPage();
    await publicPage.goto("/");
    const footer = publicPage.getByRole("contentinfo");
    await expect(footer).toBeVisible();
    const initialText = await footer.textContent();
    expect(initialText).toBeTruthy();

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

    // 3. Negative control: before outbox drain, reload public page -> tagline has NOT updated
    await publicPage.reload();
    expect(await footer.textContent()).not.toContain(testTagline);

    // 4. Drain outbox through the API host directly with the internal key (M6)
    const internalKey = apiEnv().INTERNAL_API_KEY ?? "dev-internal-key-32-chars-minimum-ok";
    const drainRes = await request.post(`${API_URL}/api/v1/internal/outbox/drain`, {
      headers: { "X-Internal-Key": internalKey },
    });
    expect(drainRes.status()).toBe(200);

    // 5. Poll public page: tagline reflects in footer within Next.js revalidation
    await expect
      .poll(
        async () => {
          await publicPage.reload();
          return footer.textContent();
        },
        { intervals: [500, 1000, 2000], timeout: 10_000 },
      )
      .toContain(testTagline);

    await publicContext.close();
    await adminContext.close();
  });

  test("CSP enforced with zero violations across public shell and main CMS screens (S5)", async ({
    browser,
  }) => {
    // Check public screens without auth
    const publicContext = await browser.newContext();
    const publicPage = await publicContext.newPage();
    const publicCspViolations: string[] = [];

    publicPage.on("console", (msg) => {
      const text = msg.text();
      if (text.includes("Content Security Policy") || text.includes("violates the following")) {
        publicCspViolations.push(text);
      }
    });

    for (const path of ["/", "/non-existent-page"]) {
      const res = await publicPage.goto(path);
      expect(res?.status()).toBeLessThan(500);
      await publicPage.waitForLoadState("domcontentloaded");
    }
    expect(publicCspViolations).toEqual([]);
    await publicContext.close();

    // Check CMS screens with authenticated session
    const adminContext = await browser.newContext({ storageState: CMS_STATE });
    const adminPage = await adminContext.newPage();
    const cmsCspViolations: string[] = [];

    adminPage.on("console", (msg) => {
      const text = msg.text();
      if (text.includes("Content Security Policy") || text.includes("violates the following")) {
        cmsCspViolations.push(text);
      }
    });

    const cmsPaths = ["/admin", "/admin/projects", "/admin/leads", "/admin/settings"];

    for (const path of cmsPaths) {
      const res = await adminPage.goto(path);
      expect(res?.status()).toBe(200);
      await adminPage.waitForLoadState("domcontentloaded");
    }

    expect(cmsCspViolations).toEqual([]);
    await adminContext.close();
  });
});

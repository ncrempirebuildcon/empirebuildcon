// The signed-out CMS pages (Phase 4 part 5, board NoirCmsLogin, SECURITY.md §1): the "Forgot
// password?" link, and the setup and reset pages opened from an emailed link. The token leaves
// the address bar as soon as the page opens, the pages send `Referrer-Policy: no-referrer`, the
// token never appears in the HTML, a used or made-up link is refused clearly, and every page is
// axe-clean and fits a phone.
//
// No sign-ins and no reset requests here (both are rate-limited per network); the journeys that
// need a real link are in account-journeys.spec.ts.
import { randomBytes } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import { seriousA11yViolations } from "../lib/auth";

const fakeToken = () => randomBytes(32).toString("base64url");

async function expectClean(page: Page, label: string) {
  await expect(page).toHaveTitle(/\S/);
  expect(await seriousA11yViolations(page), label).toEqual([]);
}

async function expectNoSideScroll(page: Page, label: string) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(
    scrollWidth,
    `${label}: ${scrollWidth}px on a ${clientWidth}px screen`,
  ).toBeLessThanOrEqual(clientWidth);
}

test("sign-in links to the forgot-password page, which is accessible", async ({ page }) => {
  await page.goto("/admin/login");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await expect(page).toHaveURL(/\/admin\/forgot$/);
  await expect(page.getByRole("heading", { level: 1, name: "Reset your password" })).toBeVisible();
  await expectClean(page, "/admin/forgot");
  // An empty address is stopped before anything is sent.
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByText("Enter your work email.", { exact: true })).toBeVisible();
  await expectClean(page, "/admin/forgot with an error");
});

test("static auth pages (/admin/setup, /admin/reset, /admin/forgot) return strict CSP directives (R2-M3)", async ({
  page,
}) => {
  for (const path of ["/admin/setup", "/admin/reset", "/admin/forgot"]) {
    const response = await page.goto(path);
    const csp =
      response?.headers()["content-security-policy"] ||
      response?.headers()["content-security-policy-report-only"] ||
      "";
    expect(csp, `${path} must carry a CSP header`).toBeTruthy();
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
  }
});

// The emailed links carry the token in the fragment (never sent to a server); links sent
// before that change carry it in the query, which still works (review L10). Setup is tried with
// the fragment, reset with the query.
for (const [kind, place] of [
  ["setup", "#"],
  ["reset", "?"],
] as const) {
  test(`the ${kind} page takes a token in ${place === "#" ? "the fragment" : "the query"} out of the address bar and sends no referrer`, async ({
    page,
  }) => {
    const token = fakeToken();
    const response = await page.goto(`/admin/${kind}${place}token=${token}`);
    // SECURITY: no Referer header from this page, CSP header present, and the token isn't in the server's HTML.
    expect(response?.headers()["referrer-policy"]).toBe("no-referrer");
    expect(
      response?.headers()["content-security-policy"] ||
        response?.headers()["content-security-policy-report-only"],
    ).toBeTruthy();
    expect(await response?.text()).not.toContain(token);
    if (place === "#") expect(response?.url()).not.toContain(token);
    await expect(page.locator('meta[name="referrer"]')).toHaveAttribute("content", "no-referrer");
    const field = page.getByLabel(kind === "setup" ? "Choose a password" : "New password", {
      exact: true,
    });
    await expect(field).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/admin/${kind}$`));
    expect(await page.evaluate(() => window.location.href)).not.toContain(token);
    await expect(field).toHaveAttribute("autocomplete", "new-password");
    await expectClean(page, `/admin/${kind}`);

    // Too short: the API's words, at the field, before anything is sent.
    await field.fill("too short");
    await page
      .getByRole("button", { name: kind === "setup" ? "Set password" : "Change password" })
      .click();
    await expect(page.getByText("Use at least 12 characters.")).toBeVisible();
    await expect(field).toHaveAttribute("aria-invalid", "true");

    // Show / Hide is a pressed toggle that never submits.
    await page.getByRole("button", { name: "Show password" }).click();
    await expect(field).toHaveAttribute("type", "text");
    await expect(page.getByRole("button", { name: "Hide password" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // A made-up token is refused by the API with a clear way forward.
    await field.fill("a long enough sentence for a password");
    await page
      .getByRole("button", { name: kind === "setup" ? "Set password" : "Change password" })
      .click();
    await expect(page.getByText("This link has expired or was used already")).toBeVisible();
    await expect(page.getByRole("link", { name: "Ask for a new link" })).toHaveAttribute(
      "href",
      "/admin/forgot",
    );
    await expectClean(page, `/admin/${kind} with a refused link`);

    // Reloading can't bring the token back: it was only ever in memory.
    await page.reload();
    await expect(page.getByText("This link is incomplete")).toBeVisible();
  });
}

test("sign-in says when a password was set from a link", async ({ page }) => {
  await page.goto("/admin/login?done=setup");
  await expect(page.getByRole("status").filter({ hasText: "Your password is set." })).toBeVisible();
  await expectClean(page, "/admin/login?done=setup");
  // Anything else in `done` is ignored.
  await page.goto("/admin/login?done=%3Cb%3Ehi%3C%2Fb%3E");
  await expect(page.getByText("Your password is")).toHaveCount(0);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the signed-out pages fit the screen", async ({ page }) => {
    for (const path of [
      "/admin/login?done=reset",
      "/admin/forgot",
      `/admin/setup#token=${fakeToken()}`,
      `/admin/reset?token=${fakeToken()}`,
    ]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expectNoSideScroll(page, path.split("?")[0] ?? path);
    }
  });
});

// Settings, consent texts and the audit log (Phase 4 part 5, board NoirCmsSettings and
// NoirCmsAudit). Each section is edited, saved and read back after a reload; the API's format
// checks show at their fields; tracking IDs and the retention period are refused for a role
// without the right (the sales session, through the API); a consent text gets a new version and
// is published in development; flags save at once; the audit log finds the changes by person,
// action and date.
//
// No new sign-ins and no public submissions: the saved super-admin and sales sessions are reused.
// Values are obviously test values in [brackets]; they stay in the local database only.
// WHY the "chat" consent purpose: publishing a new enquiry text would change the version
// leads.spec.ts sends with its public request, while it runs in parallel.
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE, SALES_STATE, apiCall, runId } from "../lib/auth";

test.use({ storageState: CMS_STATE });

const run = runId();

async function openSection(page: Page, name: RegExp) {
  await page.getByRole("tablist", { name: "Settings sections" }).getByRole("tab", { name }).click();
}

async function saveAndExpect(page: Page, form: string) {
  const section = page.getByRole("form", { name: form });
  await section.getByRole("button", { name: "Save changes" }).click();
  await expect(section.getByRole("status").filter({ hasText: /^Saved\./ })).toBeVisible();
}

test("every settings section saves, and the API's format checks show at the fields", async ({
  page,
}) => {
  test.setTimeout(120_000); // nine sections, each saved and checked
  await page.goto("/admin/settings");
  await expect(page.getByRole("tab", { name: /^Company/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // Company: a field saves and is there after a reload; the section is in the address.
  const tagline = `[E2E tagline ${run}]`;
  await page.getByLabel("Tagline").fill(tagline);
  await saveAndExpect(page, "Company settings");

  // Contacts: an impossible phone number is refused at its field, a real-shaped one saves.
  await openSection(page, /^Contacts/);
  await expect(page).toHaveURL(/\?tab=contacts$/);
  const contacts = page.getByRole("form", { name: "Contact settings" });
  await contacts.getByLabel("Sales phone").fill("12345");
  await contacts.getByRole("button", { name: "Save changes" }).click();
  await expect(contacts.getByLabel("Sales phone")).toHaveAttribute("aria-invalid", "true");
  await contacts.getByLabel("Sales phone").fill("");
  await contacts.getByLabel("Office hours").fill(`[E2E hours ${run}]`);
  await saveAndExpect(page, "Contact settings");

  // Tracking: a malformed ID is refused, a well-formed one saves (nothing loads until Phase 6).
  await openSection(page, /^Tracking/);
  const tracking = page.getByRole("form", { name: "Tracking settings" });
  await expect(tracking.getByText(/only after the visitor accepts/)).toBeVisible();
  await tracking.getByLabel("Google Tag Manager container").fill("not-an-id");
  await tracking.getByRole("button", { name: "Save changes" }).click();
  await expect(tracking.getByLabel("Google Tag Manager container")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  // A new ID each run (an earlier run's value would leave nothing to save).
  const gtm = `GTM-${run.toUpperCase().replace(/[^A-Z0-9]/g, "")}`;
  await tracking.getByLabel("Google Tag Manager container").fill(gtm);
  await saveAndExpect(page, "Tracking settings");

  // RERA: the rule is shown on and locked; the promoter number saves.
  await openSection(page, /^RERA/);
  const rule = page.getByRole("switch", { name: /^Show RERA details · On · locked/ });
  await expect(rule).toHaveAttribute("aria-checked", "true");
  await expect(rule).toHaveAttribute("aria-disabled", "true");
  // WHY not [brackets]: the field takes letters, digits, / and - only; "E2E-TEST-" marks it.
  await page.getByLabel("Promoter registration number").fill(`E2E-TEST-${run}`);
  await saveAndExpect(page, "RERA settings");

  // Email and integrations: status only, never a key; the sender name saves.
  await openSection(page, /^Email and integrations/);
  await expect(
    page.getByText("API key: set in the server environment, never shown here."),
  ).toBeVisible();
  // WHY no [brackets]: a sender name takes letters, digits, spaces and . - & ' only (it goes
  // into the From header).
  await page.getByLabel("Sender name").fill(`E2E sender ${run}`);
  await saveAndExpect(page, "Email settings");

  // SEO defaults.
  await openSection(page, /^SEO defaults/);
  await page.getByLabel("Default page title").fill(`[E2E title ${run}]`);
  await saveAndExpect(page, "SEO defaults");

  // Privacy: 1–10 years, super-admin only; set it back to the default afterwards.
  await openSection(page, /^Privacy/);
  const years = page.getByLabel("Keep leads for (years)");
  const other = (await years.inputValue()) === "4" ? "5" : "4";
  await years.fill("11");
  await page
    .getByRole("form", { name: "Privacy settings" })
    .getByRole("button", { name: "Save changes" })
    .click();
  await expect(years).toHaveAttribute("aria-invalid", "true");
  await years.fill(other);
  await saveAndExpect(page, "Privacy settings");
  await years.fill("3");
  await saveAndExpect(page, "Privacy settings");

  // Lead routing: the inbox saves.
  await openSection(page, /^Lead routing/);
  await page.getByLabel("Shared sales inbox").fill(`e2e-inbox-${run}@example.com`);
  await page
    .getByRole("form", { name: "Lead routing" })
    .getByRole("button", { name: "Save changes" })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: /New leads follow these rules/ }),
  ).toBeVisible();

  // Anyone can be taken out of the rotation (review M3); Discard puts them back unsaved.
  const rotation = page.getByRole("list", { name: "Round-robin order" });
  const listed = await rotation.getByRole("listitem").count();
  expect(listed).toBeGreaterThan(0);
  await rotation
    .getByRole("listitem")
    .first()
    .getByRole("button", { name: /^Remove from rotation/ })
    .click();
  await expect(rotation.getByRole("listitem")).toHaveCount(listed - 1);
  await page
    .getByRole("form", { name: "Lead routing" })
    .getByRole("button", { name: "Discard changes" })
    .click();
  await expect(rotation.getByRole("listitem")).toHaveCount(listed);

  // Everything is still there after a reload.
  await page.goto("/admin/settings?tab=company");
  await expect(page.getByLabel("Tagline")).toHaveValue(tagline);
  await openSection(page, /^Tracking/);
  await expect(page.getByLabel("Google Tag Manager container")).toHaveValue(gtm);
  // Leave the launch state (no tracking IDs) for the other specs and the next run.
  const cleared = await apiCall(page, "PATCH", "/api/v1/admin/settings/tracking", { gtm_id: "" });
  expect(cleared.status()).toBe(200);
});

test("unsaved settings ask before leaving, and switching sections keeps the typing", async ({
  page,
}) => {
  await page.goto("/admin/settings?tab=seo");
  await page.getByLabel("Default page title").fill(`[E2E unsaved ${run}]`);
  await openSection(page, /^Company/);
  await openSection(page, /^SEO defaults/);
  await expect(page.getByLabel("Default page title")).toHaveValue(`[E2E unsaved ${run}]`);
  await page.getByRole("link", { name: "Dashboard" }).click();
  const leave = page.getByRole("dialog", { name: "Leave without saving?" });
  await expect(leave).toBeVisible();
  await leave.getByRole("button", { name: "Stay on this page" }).click();
  await page
    .getByRole("form", { name: "SEO defaults" })
    .getByRole("button", { name: "Discard changes" })
    .click();
});

test("tracking IDs and the retention period are refused without the right", async ({ browser }) => {
  const sales = await browser.newContext({ storageState: SALES_STATE });
  const page = await sales.newPage();
  await page.goto("/admin");
  const tracking = await apiCall(page, "PATCH", "/api/v1/admin/settings/tracking", {
    gtm_id: "GTM-NOPE123",
  });
  expect(tracking.status()).toBe(403);
  const retention = await apiCall(page, "PATCH", "/api/v1/admin/settings/privacy", {
    lead_retention_years: 5,
  });
  expect(retention.status()).toBe(403);
  // Sales has no settings.read: the screen says so instead of showing settings.
  await page.goto("/admin/settings");
  await expect(page.getByText("Your role can't open Settings.")).toBeVisible();
  await sales.close();
});

test("a consent text gets a new version and is published in development", async ({ page }) => {
  await page.goto("/admin/settings?tab=consent");
  await page.getByLabel("Purpose").selectOption("chat");
  await page.getByRole("button", { name: "New version" }).click();
  const form = page.getByRole("form", { name: "New consent text version" });
  await form
    .getByLabel("Checkbox label")
    .fill(`[DRAFT] I agree to the chat assistant terms (${run}).`);
  await form
    .getByLabel("Consent text")
    .fill(`[DRAFT — awaiting the owner's approval] E2E chat text ${run}.`);
  await expect(form.getByText(/\/ 5,000 characters/)).toBeVisible();
  await form.getByRole("button", { name: "Save as draft" }).click();
  const saved = page.getByRole("status").filter({ hasText: /is saved as a draft/ });
  await expect(saved).toBeVisible();
  const version = Number((await saved.textContent())?.match(/Version (\d+)/)?.[1]);
  const card = page
    .getByRole("listitem")
    .filter({ hasText: `Version ${version}` })
    .first();
  await expect(card.getByText("DRAFT TEXT")).toBeVisible();
  await card.getByRole("button", { name: `Publish version ${version}` }).click();
  const dialog = page.getByRole("dialog", { name: `Publish version ${version}?` });
  await dialog.getByRole("button", { name: "Publish" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: `Version ${version} is now the current text` }),
  ).toBeVisible();
  await expect(card.getByText("Current")).toBeVisible();
});

test("flags save at once and the audit log finds the change", async ({ page }) => {
  await page.goto("/admin/settings?tab=flags");
  const flag = page.getByRole("switch", { name: /^Website chat assistant/ });
  const before = await flag.getAttribute("aria-checked");
  await flag.click();
  await expect(flag).toHaveAttribute("aria-checked", before === "true" ? "false" : "true");
  await flag.click();
  await expect(flag).toHaveAttribute("aria-checked", before ?? "false");
  // Locked flags can't be switched.
  await expect(page.getByText("Off · not built yet").first()).toBeVisible();

  // The audit log: today's settings and flag changes, by this person.
  await page.goto("/admin/audit");
  const entries = page.getByRole("region", { name: "Audit entries table" });
  await expect(entries).toBeVisible();
  await page
    .getByRole("group", { name: "Action" })
    .getByRole("link", { name: "Feature flags" })
    .click();
  await expect(page).toHaveURL(/action=flags/);
  await expect(entries.getByText("Feature flag switched").first()).toBeVisible();
  await entries
    .getByRole("button", { name: /^Show details of Feature flag switched/ })
    .first()
    .click();
  await expect(entries.getByRole("list", { name: "After" }).first()).toContainText("enabled:");
  // Masked IPs only (IPv4 "a.b.xxx.xxx" or an IPv6 /32), never a full address.
  // The IP is the fifth column; the before/after lines in an opened row are code too.
  for (const ip of await entries.locator("tbody tr td:nth-child(5) code").allTextContents()) {
    expect(ip).toMatch(/xxx|::\/32/);
  }
});

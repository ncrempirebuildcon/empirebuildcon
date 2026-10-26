// Account journeys (Phase 4 part 5, SECURITY.md §1), in order, with one throwaway admin made in
// the run ("E2E Invitee …"):
//   1. The super-admin invites them from Users & roles; the setup link arrives in the API's
//      development mailbox; they choose a password on /admin/setup (the token leaves the address
//      bar) and sign in (sign-in 1 of this file).
//   2. On My account they turn two-factor on: the key shown is typed into a "phone" (the test
//      computes RFC 6238 codes from it), a code confirms it, and the ten recovery codes are shown
//      once, downloadable as text, gone after "I've saved them".
//   3. They sign in again (sign-in 2): password, then the two-factor step, where a recovery code
//      works. Later the same recovery code is refused (each works once), and an app code turns
//      two-factor off.
//   4. "Forgot password?" with an address that has no account and with theirs shows the same
//      message; the reset link from the mailbox sets a new password (no sign-in needed to prove
//      it): their open session is signed out.
// The super-admin's own session is reused (CMS_STATE). This file adds exactly 2 sign-ins and 2
// reset requests (fresh addresses each run) to a run, and no public lead submissions.
//
// WHY the global `admin_2fa` flag isn't switched on here: the suite shares one database and runs
// in parallel; with the flag on, every other admin sign-in in the run (login.spec.ts, the setup
// project) would be sent to the forced set-up. The flag's own rule (the super-admin needs
// two-factor first) is checked through the API instead, and the forced set-up at sign-in reuses
// the same set-up component as My account (apps/web/src/components/admin/auth/TwoFactorSetup.tsx).
import { readFileSync } from "node:fs";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { CMS_STATE, apiCall, runId, seriousA11yViolations } from "../lib/auth";
import { latestMail, linkTo } from "../lib/mail";
import { timeStep, totp } from "../lib/totp";

// WHY 2 minutes: each journey is long, and a code may have to wait for the next 30-second step.
test.describe.configure({ mode: "serial", timeout: 120_000 });

const run = runId();
const invitee = {
  email: `e2e-invitee-${run}@example.com`,
  name: `E2E Invitee ${run}`,
  password: `first password for ${run}`,
  newPassword: `second password for ${run}`,
};
type StorageState = Awaited<ReturnType<BrowserContext["storageState"]>>;
// Shared between the steps of this file only, in memory; nothing is written to disk.
const state: { key: string; codes: string[]; lastStep: number; session?: StorageState } = {
  key: "",
  codes: [],
  lastStep: 0,
};

async function expectClean(page: Page, label: string) {
  await expect(page).toHaveTitle(/\S/);
  expect(await seriousA11yViolations(page), label).toEqual([]);
}

/** A code from the "phone" for a 30-second step not used yet (the API refuses replays). */
async function freshCode(page: Page): Promise<string> {
  while (timeStep() <= state.lastStep) await page.waitForTimeout(1000);
  state.lastStep = timeStep();
  return totp(state.key);
}

test("an invited admin sets a password from the emailed link and signs in", async ({ browser }) => {
  const admin = await browser.newContext({ storageState: CMS_STATE });
  const page = await admin.newPage();
  await page.goto("/admin/users");
  await page.getByRole("button", { name: "+ Invite user" }).click();
  const form = page.getByRole("form", { name: "Invite a user" });
  await form.getByLabel("Work email").fill(invitee.email);
  await form.getByLabel("Name").fill(invitee.name);
  await form.getByLabel("Role").selectOption("admin");
  await form.getByRole("button", { name: "Send invite link" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: `Invite sent to ${invitee.email}` }),
  ).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: invitee.email });
  await expect(row.getByText("Invited", { exact: true })).toBeVisible();

  // The setup link arrives in the development mailbox, never in the API's answers.
  const mail = await latestMail(page.request, invitee.email, { template: "setup_link" });
  const setupLink = linkTo(mail, "/admin/setup");
  await admin.close();

  const context = await browser.newContext();
  const person = await context.newPage();
  await person.goto(setupLink);
  await expect(person).toHaveURL(/\/admin\/setup$/);
  await person.getByLabel("Choose a password", { exact: true }).fill(invitee.password);
  await person.getByRole("button", { name: "Set password" }).click();
  await expect(person).toHaveURL(/\/admin\/login\?done=setup$/);
  await expect(
    person.getByRole("status").filter({ hasText: "Your password is set." }),
  ).toBeVisible();

  // Sign-in 1.
  await person.getByLabel("Email").fill(invitee.email);
  await person.getByLabel("Password", { exact: true }).fill(invitee.password);
  await person.getByRole("button", { name: "Sign in" }).click();
  await expect(person).toHaveURL(/\/admin$/);
  await expect(person.getByText(`Signed in as ${invitee.name}`)).toBeVisible();

  // The same link can't be used twice.
  const reuse = await context.newPage();
  await reuse.goto(setupLink);
  await reuse.getByLabel("Choose a password", { exact: true }).fill(`another password ${run}`);
  await reuse.getByRole("button", { name: "Set password" }).click();
  await expect(reuse.getByText("This link has expired or was used already")).toBeVisible();
  await reuse.close();

  // 2. Two-factor on, from My account.
  await person.getByRole("link", { name: "My account" }).click();
  const panel = person.getByRole("region", { name: "Two-factor sign-in" });
  await expect(panel.getByText("Status: Off")).toBeVisible();
  await panel.getByRole("button", { name: "Turn on two-factor" }).click();
  await panel.getByLabel("Current password", { exact: true }).fill(invitee.password);
  await panel.getByRole("button", { name: "Continue" }).click();
  await expect(
    panel.getByRole("img", { name: /^QR code for your authenticator app\. If you can't scan it/ }),
  ).toBeVisible();
  state.key = (await panel.locator("code").first().textContent()) ?? "";
  expect(state.key.replace(/\s/g, "")).toMatch(/^[A-Z2-7]{16,}$/);
  const codeField = panel.getByLabel("6-digit code from the app");
  await expect(codeField).toHaveAttribute("autocomplete", "one-time-code");
  await expect(codeField).toHaveAttribute("inputmode", "numeric");
  await expectClean(person, "two-factor set-up");
  await codeField.fill(await freshCode(person));
  await panel.getByRole("button", { name: "Turn on two-factor" }).click();

  const codes = panel.getByRole("list", { name: "Recovery codes" });
  await expect(codes.getByRole("listitem")).toHaveCount(10);
  // Shown once: no Cancel now; the only way on is "I've saved them" (review L7). The status is
  // already read again, so it can't offer "Turn on" a second time.
  await expect(panel.getByRole("button", { name: "Cancel" })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Turn on two-factor" })).toHaveCount(0);
  state.codes = (await codes.locator("code").allTextContents()).map((c) => c.trim());
  await expectClean(person, "recovery codes");
  const downloading = person.waitForEvent("download");
  await panel.getByRole("button", { name: "Download as text" }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe("empire-cms-recovery-codes.txt");
  const text = readFileSync((await download.path()) ?? "", "utf8");
  for (const code of state.codes) expect(text).toContain(code);
  const done = panel.getByRole("button", { name: "Done" });
  await expect(done).toHaveAttribute("aria-disabled", "true");
  await panel.getByLabel("I've saved my recovery codes somewhere safe").check();
  await done.click();
  await expect(
    panel.getByRole("status").filter({ hasText: "Two-factor sign-in is on." }),
  ).toBeVisible();
  // Shown once: the codes and the key are gone from the page.
  await expect(codes).toHaveCount(0);
  await expect(person.getByText(state.codes[0] ?? "-")).toHaveCount(0);
  await expect(panel.getByText(/Status: On · 10 recovery codes left/)).toBeVisible();
  await context.close();
});

test("two-factor at sign-in takes a recovery code once, and an app code turns it off", async ({
  browser,
}) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  // Sign-in 2: the password is right, so the second step follows (no session yet).
  await page.goto("/admin/login");
  await page.getByLabel("Email").fill(invitee.email);
  await page.getByLabel("Password", { exact: true }).fill(invitee.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Two-factor check" })).toBeVisible();
  await expect(page.getByLabel("6-digit code")).toHaveAttribute("autocomplete", "one-time-code");
  expect((await context.cookies()).some((c) => c.name === "__Host-empire_session")).toBe(false);
  await expectClean(page, "two-factor step");

  const [first] = state.codes;
  await page.getByRole("button", { name: "Use a recovery code" }).click();
  await page.getByLabel("Recovery code").fill(first ?? "");
  await page.getByRole("button", { name: "Verify and continue" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText(`Signed in as ${invitee.name}`)).toBeVisible();

  // The used recovery code is refused the second time; a fresh app code works.
  await page.goto("/admin/account");
  const panel = page.getByRole("region", { name: "Two-factor sign-in" });
  await expect(panel.getByText(/9 recovery codes left/)).toBeVisible();
  await panel.getByRole("button", { name: "Turn off two-factor" }).click();
  const off = panel.getByRole("form", { name: "Turn off two-factor" });
  await off.getByLabel("Current password", { exact: true }).fill(invitee.password);
  await off.getByRole("button", { name: "Use a recovery code" }).click();
  await off.getByLabel("Recovery code").fill(first ?? "");
  await off.getByRole("button", { name: "Turn off two-factor" }).click();
  await expect(off.getByRole("alert")).toBeVisible();
  await off.getByLabel("Current password", { exact: true }).fill(invitee.password);
  await off.getByRole("button", { name: "Use a code from the app instead" }).click();
  await off.getByLabel("6-digit code from the app").fill(await freshCode(page));
  await off.getByRole("button", { name: "Turn off two-factor" }).click();
  await expect(
    panel.getByRole("status").filter({ hasText: "Two-factor sign-in is off." }),
  ).toBeVisible();
  await expect(panel.getByText("Status: Off")).toBeVisible();

  // Kept for the reset journey: a password reset must sign this session out.
  state.session = await context.storageState();
  await context.close();
});

test("forgot password: the same message for any address, and the link signs old sessions out", async ({
  browser,
  page,
}) => {
  const unknown = `e2e-nobody-${run}@example.com`;
  await page.goto("/admin/forgot");
  await page.getByLabel("Work email").fill(unknown);
  await page.getByRole("button", { name: "Send reset link" }).click();
  const message = page.getByRole("status").filter({ hasText: "Check your email" });
  await expect(message).toBeVisible();
  const forUnknown = await message.textContent();

  await page.goto("/admin/forgot");
  await page.getByLabel("Work email").fill(invitee.email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(message).toBeVisible();
  expect(await message.textContent()).toBe(forUnknown);

  const mail = await latestMail(page.request, invitee.email, { template: "reset_link" });
  const resetLink = linkTo(mail, "/admin/reset");
  await page.goto(resetLink);
  await expect(page).toHaveURL(/\/admin\/reset$/);
  const response = page.waitForResponse("**/api/v1/auth/password/reset");
  await page.getByLabel("New password", { exact: true }).fill(invitee.newPassword);
  await page.getByRole("button", { name: "Change password" }).click();
  expect((await response).status()).toBe(204);
  await expect(page).toHaveURL(/\/admin\/login\?done=reset$/);

  // The session from the two-factor journey was signed out by the reset.
  const old = await browser.newContext({ storageState: state.session });
  const me = await old.request.get("/api/v1/auth/me");
  expect(me.status()).toBe(401);
  await old.close();
});

test("the super-admin can't switch admin_2fa on without their own two-factor", async ({
  browser,
}) => {
  const admin = await browser.newContext({ storageState: CMS_STATE });
  const page = await admin.newPage();
  await page.goto("/admin/settings?tab=flags");
  const flag = page.getByRole("switch", { name: /^Two-factor sign-in for admins/ });
  await expect(flag).toHaveAttribute("aria-checked", "false");
  await expect(flag).toHaveAttribute("aria-disabled", "true");
  await expect(
    page.getByText(/Turn on two-factor sign-in for your own account first/),
  ).toBeVisible();
  const refused = await apiCall(page, "PATCH", "/api/v1/admin/flags/admin_2fa", { enabled: true });
  expect([403, 409]).toContain(refused.status());
  await admin.close();
});

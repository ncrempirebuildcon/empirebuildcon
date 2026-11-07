/**
 * Tags after consent, end to end (task 6.3, D-058). With tracking IDs set in the CMS:
 *   - the banner shows, and nothing is requested from Google or Meta before a choice;
 *   - "Reject all" keeps it that way, also after a reload;
 *   - "Accept all" loads the Google tag and the Meta Pixel, with no CSP violation (for the tags'
 *     first scripts; their stubs here make no further requests);
 *   - narrowing the choice reloads the page, and the Pixel doesn't load again;
 *   - a sent enquiry reaches the Pixel with its reference as the eventID.
 * Third-party requests are answered here (never reach the internet) and recorded.
 *
 * WHY serial: it changes Settings → Tracking, which every public page reads. It runs after the
 * main project, and puts the IDs back to empty at the end.
 */
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";

test.use({ storageState: CMS_STATE });
test.describe.configure({ mode: "serial" });

const IDS = { ga4_id: "G-E2E0000001", meta_pixel_id: "100000000000001" };
const THIRD_PARTY = /googletagmanager\.com|google-analytics\.com|facebook\.net|facebook\.com/;

async function visitor(
  context: BrowserContext,
): Promise<{ page: Page; seen: string[]; csp: string[] }> {
  const seen: string[] = [];
  await context.route(THIRD_PARTY, async (route) => {
    seen.push(route.request().url());
    const isScript = /\.js|gtag\/js/.test(route.request().url());
    await route.fulfill(
      isScript
        ? { status: 200, contentType: "application/javascript", body: "/* e2e stub */" }
        : { status: 204, body: "" },
    );
  });
  const page = await context.newPage();
  const csp: string[] = [];
  page.on("console", (msg) => {
    if (/Content Security Policy/i.test(msg.text())) csp.push(msg.text());
  });
  return { page, seen, csp };
}

async function bannerOn(page: Page, path: string): Promise<void> {
  // The settings change reaches the cached pages within seconds (D-054).
  await expect
    .poll(
      async () => {
        await page.goto(path);
        return page.getByRole("region", { name: "Cookie choices" }).count();
      },
      { intervals: [500, 1000, 2000], timeout: 20_000 },
    )
    .toBe(1);
}

test.beforeAll(async ({ browser }) => {
  const admin = await (await browser.newContext({ storageState: CMS_STATE })).newPage();
  await admin.goto("/admin");
  const res = await apiCall(admin, "PATCH", "/api/v1/admin/settings/tracking", IDS);
  expect(res.status()).toBe(200);
});

test.afterAll(async ({ browser }) => {
  const admin = await (await browser.newContext({ storageState: CMS_STATE })).newPage();
  await admin.goto("/admin");
  await apiCall(admin, "PATCH", "/api/v1/admin/settings/tracking", {
    ga4_id: "",
    gtm_id: "",
    google_ads_id: "",
    meta_pixel_id: "",
  });
});

test("nothing reaches Google or Meta before a choice, or after Reject all", async ({ browser }) => {
  const context = await browser.newContext();
  const { page, seen } = await visitor(context);
  await bannerOn(page, "/projects");
  expect(seen).toEqual([]);

  await page.getByRole("button", { name: /Reject all/ }).click();
  await expect(page.getByRole("region", { name: "Cookie choices" })).toBeHidden();
  await page.reload({ waitUntil: "networkidle" });
  await page.goto("/contact", { waitUntil: "networkidle" });
  // Hydrated and settled (the banner stays closed), and still nothing reached Google or Meta.
  await expect(page.getByRole("button", { name: "Cookie settings" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Cookie choices" })).toBeHidden();
  expect(seen).toEqual([]);
  await context.close();
});

test("Accept all loads the Google tag and the Pixel, within the CSP", async ({ browser }) => {
  const context = await browser.newContext();
  const { page, seen, csp } = await visitor(context);
  await bannerOn(page, "/projects");
  await page.getByRole("button", { name: /Accept all/ }).click();
  await expect.poll(() => seen.some((u) => u.includes("gtag/js?id=G-E2E0000001"))).toBe(true);
  await expect.poll(() => seen.some((u) => u.includes("connect.facebook.net/"))).toBe(true);
  expect(csp).toEqual([]);

  // Narrowing the choice reloads the page, and from then on nothing new loads.
  await page.getByRole("button", { name: "Cookie settings" }).click();
  await page.getByRole("switch", { name: /Marketing/ }).click();
  const before = seen.length;
  await Promise.all([
    page.waitForEvent("load"),
    page.getByRole("button", { name: /Save choices/ }).click(),
  ]);
  await page.waitForLoadState("networkidle");
  // After the reload GA4 (still allowed) loads again, and the Pixel does not.
  await expect.poll(() => seen.slice(before).some((u) => u.includes("gtag/js"))).toBe(true);
  expect(seen.slice(before).some((u) => u.includes("facebook.net"))).toBe(false);
  await context.close();
});

test("a sent enquiry reaches the Pixel with its reference as the eventID", async ({ browser }) => {
  const context = await browser.newContext();
  const { page } = await visitor(context);
  // The API's answer is stubbed: no lead is created by this test.
  await context.route("**/api/v1/public/leads", (route) =>
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ reference: "EMP-E2E01", message: "Thank you." }),
    }),
  );
  await bannerOn(page, "/contact");
  await page.getByRole("button", { name: /Accept all/ }).click();
  const form = page.getByTestId("lead-form-enquiry");
  await form.getByLabel("Your name").fill("E2E Tags Lead");
  await form.getByLabel("Mobile number").fill("9876543210");
  await form.getByTestId("consent-required").check();
  await form.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("lead-success")).toContainText("EMP-E2E01");
  // fbevents.js is a stub here, so the Pixel's calls stay in its queue for us to read.
  const queue = await page.evaluate(() => (window as { fbq?: { queue: unknown[][] } }).fbq?.queue);
  expect(queue).toContainEqual(["track", "Lead", {}, { eventID: "EMP-E2E01" }]);
  await context.close();
});

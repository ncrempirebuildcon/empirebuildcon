// Lead journey (spec Phase 4 part 3, QA journey 1): a visitor asks for a site visit through the
// public API with the current consent version → the lead arrives unread in the inbox → opening it
// marks it read → a note → Contacted → Site visit → the visit is confirmed with a time → the
// dashboard counts and lists show it → the CSV export downloads with its header row (and is
// audited); the calendar reschedules the visit. Plus: a lead added by hand (owner, details, spam,
// mark unread) and erasing a lead's personal data through the confirm dialog.
import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { CMS_STATE, apiCall, runId } from "../lib/auth";
import {
  cancelEarlierTestVisits,
  currentConsent,
  istDate,
  manualLead,
  publishedProject,
  requestSiteVisit,
  sampleProjectId,
  testMobile,
} from "../lib/leads";

// Signed in once by auth.setup.ts (the API limits sign-ins per network).
test.use({ storageState: CMS_STATE });
// WHY serial: tests in this spec create, mutate, reassign, erase and count leads.
// Running them serially avoids dashboard count drift and dirty-form dialog races between tests.
test.describe.configure({ mode: "serial" });

// The documented CSV columns (apps/api/src/empire_api/leads/export.py), in order.
const CSV_HEADER =
  "reference,created_at,name,phone,email,project,configuration,source,status,lost_reason," +
  "lost_reason_note,owner,assigned_at,read_at,last_activity_at,message,page_url,referrer,utm_source,utm_medium," +
  "utm_campaign,utm_term,utm_content,gclid,gbraid,wbraid,fbclid,msclkid,preferred_bhk," +
  "budget_max_inr,preferred_contact_time,language,consent_text_version,consented_at," +
  "consent_note,marketing_consent,duplicate_of,is_spam,is_sample,erased_at";

test("a public site-visit request goes from the inbox to a confirmed visit and an export", async ({
  page,
}) => {
  const project = await publishedProject(page);
  const consent = await currentConsent(page);
  const lead = await requestSiteVisit(project, consent);

  // 1. The inbox shows it, unread (bold, and "Unread:" for screen readers), with a masked number.
  await page.goto("/admin");
  await page
    .getByRole("navigation", { name: "Sections" })
    .getByRole("link", { name: /^Leads/ })
    .click();
  await expect(page).toHaveURL(/\/admin\/leads$/);
  await page.getByLabel("Search").fill(lead.reference);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page).toHaveURL(new RegExp(`q=${lead.reference}`));
  const table = page.getByRole("table", { name: "Leads, newest first" });
  const unreadRow = table.getByRole("row").filter({ hasText: lead.reference });
  await expect(unreadRow.getByRole("rowheader")).toContainText(`Unread: ${lead.name}`);
  const digits = lead.phone.replace(/\D/g, "");
  await expect(unreadRow).toContainText(`+91 ${digits.slice(0, 2)}xxxxxx${digits.slice(8)}`);
  await expect(unreadRow).not.toContainText(digits);

  // 2. Opening it marks it read; the full number is there with tap-to-call and WhatsApp.
  await unreadRow.getByRole("link", { name: `Unread: ${lead.name}` }).click();
  await expect(page.getByRole("heading", { level: 1, name: lead.name })).toBeVisible();
  const summary = page.getByRole("region", { name: "Lead summary" });
  await expect(summary.getByRole("link", { name: `Call ${lead.name}` })).toHaveAttribute(
    "href",
    `tel:+91${digits}`,
  );
  await expect(summary.getByRole("link", { name: /^WhatsApp/ })).toHaveAttribute(
    "href",
    `https://wa.me/91${digits}`,
  );
  const leadId = page.url().split("/").pop() ?? "";
  await expect
    .poll(async () => {
      const response = await apiCall(page, "GET", `/api/v1/admin/leads/${leadId}`);
      return ((await response.json()) as { read_at: string | null }).read_at !== null;
    })
    .toBe(true);

  // The consent record shows the text version, the label shown and that marketing was not given.
  const consentPanel = page.getByRole("region", { name: "Consent record" });
  await expect(consentPanel).toContainText(`Version ${consent.version}`);
  await expect(consentPanel).toContainText(consent.checkbox_label);
  await expect(consentPanel).toContainText("News and offers: not given");
  await expect(page.getByRole("region", { name: "Source and campaign" })).toContainText(
    lead.campaign,
  );

  // 3. A note.
  const note = `Prefers a weekend visit (${runId()})`;
  await page.getByLabel("Add a note").fill(note);
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Note added." })).toBeAttached();
  await expect(page.getByRole("list", { name: "Timeline, newest first" })).toContainText(note);

  // 4. Contacted, then Site visit; each move is announced and lands in the timeline.
  const stages = page.getByRole("group", { name: "Choose a stage" });
  for (const stage of ["Contacted", "Site visit"]) {
    await stages.getByRole("button", { name: new RegExp(`^${stage}`) }).click();
    await page.getByRole("button", { name: "Save stage" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: `Stage changed to ${stage}.` }),
    ).toBeAttached();
    await expect(
      stages.getByRole("button", { name: new RegExp(`^${stage}\\W+Current$`) }),
    ).toHaveAttribute("aria-pressed", "true");
  }
  await expect(page.getByRole("list", { name: "Timeline, newest first" })).toContainText(
    "Contacted → Site visit",
  );

  // 5. Confirm the visit with the time agreed by phone (India time).
  const visitPanel = page.getByRole("region", { name: "Site visit" });
  await expect(visitPanel).toContainText("Requested · to confirm");
  await visitPanel.getByLabel("Date agreed").fill(istDate(1));
  await visitPanel.getByLabel("Time agreed (IST)").fill("11:00");
  await visitPanel.getByRole("button", { name: "Confirm visit" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: /^Visit confirmed for .*11:00 am\.$/ }),
  ).toBeAttached();
  await expect(visitPanel).toContainText("Confirmed");

  // The calendar has it at 11:00 IST; rescheduling there to 12:30 moves it to the afternoon.
  await visitPanel.getByRole("link", { name: "Open the calendar" }).click();
  await expect(page).toHaveURL(/\/admin\/site-visits\?/);
  await page.getByRole("radio", { name: "Week" }).click();
  const week = page.getByRole("table", { name: /^Site visits, / });
  await expect(week.getByRole("button", { name: new RegExp(lead.name) })).toContainText(
    "Confirmed · 11:00 am",
  );
  const panel = page.getByRole("complementary", { name: lead.name });
  await expect(panel.getByRole("link", { name: /^Open lead/ })).toBeVisible();
  await panel.getByLabel("Time agreed (IST)").fill("12:30");
  await panel.getByRole("button", { name: "Save new time" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: /^Visit moved to .*12:30 pm\.$/ }),
  ).toBeAttached();
  await expect(
    week
      .getByRole("row", { name: /^Afternoon/ })
      .getByRole("button", { name: new RegExp(lead.name) }),
  ).toContainText("Confirmed · 12:30 pm");

  // 6. The dashboard: the visit is upcoming, and the "this week" tile opens the calendar.
  await cancelEarlierTestVisits(page);
  await page.goto("/admin");
  const upcoming = page.getByRole("region", { name: "Upcoming site visits" });
  await expect(upcoming.getByRole("link", { name: lead.name })).toBeVisible();
  const counts = page.getByRole("list", { name: "Counts" });
  await expect(counts.getByRole("link")).not.toHaveCount(0);
  await page.reload();
  const dashboard = await apiCall(page, "GET", "/api/v1/admin/dashboard");
  const body = (await dashboard.json()) as {
    counts: Array<{ key: string; label: string; count: number; link: string }>;
  };
  // WHY no exact numbers here: specs running alongside add drafts and leads between the page
  // and the API call. Exact counts are checked in dashboard-counts.serial.spec.ts, alone.
  for (const count of body.counts) {
    await expect(
      counts.getByRole("link", { name: new RegExp(`^${escapeRegExp(count.label)} \\d`) }),
    ).toHaveAttribute("href", count.link);
  }
  const newLeads = body.counts.find((count) => count.key === "leads.new");
  if (newLeads) {
    await counts.getByRole("link", { name: new RegExp(`^${newLeads.label}`) }).click();
    await expect(page).toHaveURL(/\/admin\/leads\?.*status=new/);
  }

  // 7. Export the filtered list: a warning first, then a real CSV download with the header row.
  // SECURITY: without the session's CSRF token the API refuses (a link elsewhere can't export).
  const bare = await page.request.get(`/api/v1/admin/leads/export.csv?q=${lead.reference}`);
  expect(bare.status()).toBe(403);
  await page.goto(`/admin/leads?q=${lead.reference}`);
  await page.getByRole("button", { name: "Export CSV" }).click();
  const dialog = page.getByRole("dialog", { name: "Export these leads?" });
  await expect(dialog).toContainText("personal data");
  await expect(dialog).toContainText("audit log");
  const download = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "Download CSV" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.csv$/);
  const text = (await readFile(await file.path(), "utf8")).replace(/^\uFEFF/, "");
  const [header, ...rows] = text.trim().split(/\r?\n/);
  expect(header).toBe(CSV_HEADER);
  expect(rows).toHaveLength(1);
  expect(rows[0]).toContain(lead.reference);
  await expect(dialog).toBeHidden();

  // The export is on the lead's timeline.
  await page.goto(`/admin/leads/${leadId}`);
  await expect(page.getByRole("list", { name: "Timeline, newest first" })).toContainText(
    "Included in a CSV export",
  );
});

test("staff add a lead by hand, then change its owner, details, spam flag and read state", async ({
  page,
}) => {
  const name = `E2E Walk-in ${runId()}`;
  const me = (await (await apiCall(page, "GET", "/api/v1/auth/me")).json()) as { id: string };

  await page.goto("/admin/leads");
  await page.getByRole("button", { name: "+ Add lead" }).click();
  const add = page.getByRole("dialog", { name: "Add a lead" });
  await add.getByLabel("Name").fill(name);
  await add.getByLabel("Mobile").fill(testMobile());
  await add.getByLabel("How they got in touch").selectOption({ label: "Phone call" });
  await add.getByLabel("How they agreed to be contacted").fill("Verbal on phone call (test)");
  await add.getByRole("button", { name: "Add lead" }).click();
  await expect(page).toHaveURL(/\/admin\/leads\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  // A manual lead's consent record is the staff note, with no text version.
  const consent = page.getByRole("region", { name: "Consent record" });
  await expect(consent).toContainText("Recorded by staff: “Verbal on phone call (test)”");
  await expect(consent).toContainText("None · added by staff");

  // Owner: to the sales inbox and back.
  const summary = page.getByRole("region", { name: "Lead summary" });
  const owner = summary.getByLabel("Owner");
  await owner.selectOption({ value: "unassigned" });
  await expect(
    page.getByRole("status").filter({ hasText: "Lead moved to the sales inbox." }),
  ).toBeAttached();
  await owner.selectOption({ value: me.id });
  await expect(page.getByRole("status").filter({ hasText: /^Owner changed to / })).toBeAttached();

  // Details from the call.
  const enquiry = page.getByRole("region", { name: "Enquiry" });
  await enquiry.getByRole("button", { name: "Edit details" }).click();
  await enquiry.getByLabel("Interest (BHK)").fill("3");
  await enquiry.getByLabel("Budget up to (₹)").fill("12500000");
  await enquiry.getByRole("button", { name: "Save details" }).click();
  await expect(enquiry).toContainText("3 BHK");
  await expect(enquiry).toContainText("up to ₹ 1.25 Cr");
  const timeline = page.getByRole("list", { name: "Timeline, newest first" });
  await expect(timeline).toContainText("Details changed");
  await expect(timeline).toContainText(/Changed: .*(interest|budget)/);

  // Spam, and back.
  await summary.getByRole("button", { name: "Mark as spam" }).click();
  await expect(summary.getByText("Spam", { exact: true })).toBeVisible();
  await summary.getByRole("button", { name: "Not spam" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "No longer marked as spam." }),
  ).toBeAttached();

  // Lost needs a reason; "Other reason" needs it in words.
  await page
    .getByRole("group", { name: "Choose a stage" })
    .getByRole("button", { name: "Lost" })
    .click();
  await page.getByLabel("Reason", { exact: false }).first().selectOption({ label: "Other reason" });
  await page.getByRole("button", { name: "Save stage" }).click();
  await expect(page.getByText("Say in a few words why the lead was lost.")).toBeVisible();
  await page.getByLabel("Reason in words").fill("Moved abroad (test)");
  await page.getByRole("button", { name: "Save stage" }).click();
  await expect(page.getByText("Lost because:")).toContainText("Moved abroad (test)");
  await expect(page.getByRole("list", { name: "Timeline, newest first" })).toContainText(
    "reason: Moved abroad (test)",
  );

  // Mark unread: back to the inbox, where it is unread again.
  await summary.getByRole("button", { name: "Mark unread" }).click();
  // WHY 15 s: the inbox loads after the API call; on a busy machine (two workers, a growing
  // local database) that took more than the default 5 s once. Only the wait changes.
  await expect(page).toHaveURL(/\/admin\/leads$/, { timeout: 15_000 });
  await page.getByLabel("Search").fill(name);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page).toHaveURL(/[?&]q=E2E/);
  await expect(
    page
      .getByRole("table", { name: "Leads, newest first" })
      .getByRole("rowheader", { name: `Unread: ${name}` }),
  ).toBeVisible();
});

test("typed work on a lead or in Add lead asks before it is thrown away", async ({ page }) => {
  const name = `E2E Unsaved ${runId()}`;
  const lead = await manualLead(page, name);
  await page.goto(`/admin/leads/${lead.id}`);
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  const note = page.getByLabel("Add a note");
  await note.fill("Half-written note");

  // A link away asks first; "Stay on this page" keeps the typing.
  await page.getByRole("banner").getByRole("link", { name: "Leads" }).click();
  const leave = page.getByRole("dialog", { name: "Leave without saving?" });
  await expect(leave).toBeVisible();
  await leave.getByRole("button", { name: "Stay on this page" }).click();
  await expect(page).toHaveURL(new RegExp(`/admin/leads/${lead.id}$`));
  await expect(note).toHaveValue("Half-written note");

  // "Mark unread" goes back to the inbox through the same question.
  await page
    .getByRole("region", { name: "Lead summary" })
    .getByRole("button", { name: "Mark unread" })
    .click();
  await expect(leave).toBeVisible();
  await leave.getByRole("button", { name: "Leave without saving" }).click();
  await expect(page).toHaveURL(/\/admin\/leads$/);

  // Add lead: Cancel with something typed asks "Discard this lead?".
  await page.getByRole("button", { name: "+ Add lead" }).click();
  const add = page.getByRole("dialog", { name: "Add a lead" });
  await add.getByLabel("Name").fill("Someone");
  await add.getByRole("button", { name: "Cancel" }).click();
  const discard = page.getByRole("dialog", { name: "Discard this lead?" });
  await discard.getByRole("button", { name: "Keep editing" }).click();
  await expect(add.getByLabel("Name")).toHaveValue("Someone");
  await add.getByRole("button", { name: "Cancel" }).click();
  await discard.getByRole("button", { name: "Discard" }).click();
  await expect(add).toBeHidden();
});

test("a super-admin erases a lead's personal data after a clear warning", async ({ page }) => {
  // Two enquiries from one number about different things: not repeats of each other, so the
  // dialog offers to erase the other one too ("every lead with this phone number").
  const run = runId();
  const name = `E2E Erase ${run}`;
  const phone = testMobile();
  const lead = await manualLead(page, name, undefined, { phone });
  const other = await manualLead(page, `E2E Erase other ${run}`, undefined, {
    phone,
    projectId: await sampleProjectId(page),
  });

  await page.goto(`/admin/leads/${lead.id}`);
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await page.getByLabel("Add a note").fill("Asked to be removed (browser test)");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByRole("list", { name: "Timeline, newest first" })).toContainText(
    "Asked to be removed",
  );

  await page.getByRole("button", { name: "Erase personal data" }).click();
  const dialog = page.getByRole("dialog", { name: "Erase this person's data?" });
  await expect(dialog).toContainText("It cannot be undone.");
  await expect(dialog).toContainText("the text of every note");
  await expect(dialog).toContainText("Erases: this lead.");
  // Cancel is focused first, so Enter by habit never erases anything.
  await expect(dialog.getByRole("button", { name: "Keep the data" })).toBeFocused();
  // Never pre-ticked; ticking it widens the erasure to the other lead with this number.
  const wider = dialog.getByLabel("Also erase the 1 other lead with this phone number", {
    exact: false,
  });
  await expect(wider).not.toBeChecked();
  await wider.check();
  await expect(dialog).toContainText("every other lead with this phone number (2 leads in all)");
  await dialog.getByRole("button", { name: "Erase personal data" }).click();
  await expect(dialog).toBeHidden();

  await expect(page.getByRole("heading", { level: 1, name: "[erased]" })).toBeVisible();
  await expect(page.getByText(/Personal data erased on/)).toBeVisible();
  await expect(page.getByRole("list", { name: "Timeline, newest first" })).not.toContainText(
    "Asked to be removed",
  );
  await expect(page.getByRole("link", { name: /^Call/ })).toHaveCount(0);
  // The reference stays, so the record still adds up.
  await expect(page.getByRole("region", { name: "Lead summary" })).toContainText(lead.reference);
  // The other lead with the same number is erased too.
  const erasedOther = await apiCall(page, "GET", `/api/v1/admin/leads/${other.id}`);
  expect(((await erasedOther.json()) as { name: string }).name).toBe("[erased]");
});

/** `text` as a literal inside a regular expression. */
function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

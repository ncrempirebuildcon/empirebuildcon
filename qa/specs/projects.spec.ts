// CMS projects journey (spec Phase 4 parts 1 and 2): catalogue city and locality → new project →
// location → configuration with area and price → publish blockers → tower order → media (photos,
// order, cover, hide, labels, a PDF, the share image, a floor plan) → RERA QR → publish →
// unpublish → archive.
// Files are made in the test (lib/files.ts) and go to the API's fake store (lib/env.ts).
import { expect, test, type Locator, type Page } from "@playwright/test";
import { CMS_STATE, apiCall, runId, seriousA11yViolations } from "../lib/auth";
import { samplePdf, samplePhoto, sampleQr, type TestFile } from "../lib/files";

// Signed in once by auth.setup.ts (the API limits sign-ins per network).
test.use({ storageState: CMS_STATE });

// WHY serial: each step builds on the one before (the same project), like a real editor session.
test.describe.configure({ mode: "serial" });

const id = runId();
const cityName = `E2E City ${id}`;
const localityName = `E2E Locality ${id}`;
const projectName = `E2E Project ${id}`;
let projectUrl = "";

async function openTab(page: Page, name: string) {
  await page.getByRole("tab", { name }).click();
  await expect(page.getByRole("tab", { name })).toHaveAttribute("aria-selected", "true");
}

/** Chooses files through the real file chooser that `button` opens (no hidden-input shortcut). */
async function upload(page: Page, button: Locator, files: TestFile[]) {
  const chooser = page.waitForEvent("filechooser");
  await button.click();
  await (await chooser).setFiles(files);
}

test("an admin adds a city and a locality in the catalogue", async ({ page }) => {
  await page.goto("/admin");
  await page
    .getByRole("navigation", { name: "Sections" })
    .getByRole("link", { name: "Catalogue" })
    .click();
  await expect(page).toHaveURL(/\/admin\/catalogue$/);
  await expect(page.getByRole("heading", { level: 1, name: "Catalogue" })).toBeVisible();

  const cities = page.getByRole("region", { name: "Cities" }).first();
  await page.getByRole("button", { name: "+ Add city" }).click();
  const cityForm = page.getByRole("form", { name: "Add city" });
  await cityForm.getByLabel("Name").fill(cityName);
  await expect(cityForm.getByLabel("State")).toHaveValue("Uttar Pradesh");
  await cityForm.getByRole("button", { name: "Save" }).click();
  await expect(cities.getByRole("rowheader", { name: cityName })).toBeVisible();

  await page.getByRole("button", { name: "+ Add locality" }).click();
  const localityForm = page.getByRole("form", { name: "Add locality" });
  await localityForm.getByLabel("City").selectOption({ label: cityName });
  await localityForm.getByLabel("Name").fill(localityName);
  await localityForm.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("rowheader", { name: localityName })).toBeVisible();
});

test("an admin creates a project and sees what blocks publishing", async ({ page }) => {
  await page.goto("/admin/projects");
  await page.getByRole("link", { name: "+ New project" }).click();
  await expect(page).toHaveURL(/\/admin\/projects\/new$/);

  await page.getByLabel("Project name").fill(projectName);
  await page.getByLabel("Construction status").selectOption({ label: "Under construction" });
  await page.getByLabel("City (optional)").selectOption({ label: `${cityName}, Uttar Pradesh` });
  await page.getByRole("button", { name: "Create draft" }).click();

  await expect(page).toHaveURL(/\/admin\/projects\/[0-9a-f-]{36}$/);
  projectUrl = new URL(page.url()).pathname;
  await expect(page.getByRole("heading", { level: 1, name: projectName })).toBeVisible();

  const checklist = page.locator("#publish-checklist");
  await expect(checklist.getByText("RERA registration number missing")).toBeVisible();
  await expect(checklist.getByText("RERA QR code missing")).toBeVisible();
  await expect(checklist.getByText("Add at least one configuration")).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish" })).toHaveAttribute(
    "aria-disabled",
    "true",
  );

  // The API refuses to publish too, listing the same blockers (problem+json 409).
  const projectId = projectUrl.split("/").pop();
  const refused = await apiCall(page, "POST", `/api/v1/admin/projects/${projectId}/publish`);
  expect(refused.status()).toBe(409);
});

test("an admin sets the locality and the RERA number", async ({ page }) => {
  await page.goto(projectUrl);
  await openTab(page, "Location");
  await page.getByLabel("Locality").selectOption({ label: localityName });
  await page.getByLabel("PIN code").fill("201301");
  // A full plus code pasted with a place name: the pin is set and only the code is kept.
  await page.getByLabel("Paste a Google Maps link or plus code").fill("7JWV8XX8+XX Noida");
  await page.getByRole("button", { name: "Get pin" }).click();
  await expect(page.getByText(/Pin set to/)).toBeVisible();
  const code = page.getByRole("definition").filter({ hasText: "7JWV8XX8+XX" });
  await expect(code).toBeVisible();
  await expect(code).not.toContainText("Noida");

  await openTab(page, "Details");
  await page.getByLabel("RERA registration number").fill("UPRERAPRJ-E2E-01");
  await page.getByLabel("Price from (₹)").fill("7800000");
  await expect(page.getByText("Shows as ₹ 78 L")).toBeVisible();

  // With unsaved changes, Duplicate (which opens the copy) waits for a save.
  const duplicate = page.getByRole("button", { name: "Duplicate" });
  await expect(duplicate).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByText("Save your changes before duplicating.")).toBeVisible();

  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
  const checklist = page.locator("#publish-checklist");
  await expect(checklist.getByText("RERA registration number missing")).toHaveCount(0);
  await expect(page.getByText(`${localityName}, ${cityName}`)).toBeVisible();
  await expect(duplicate).not.toHaveAttribute("aria-disabled", "true");
});

test("an admin adds a configuration with carpet area and price", async ({ page }) => {
  await page.goto(`${projectUrl}?tab=configurations`);
  await page.getByRole("button", { name: "+ Add configuration" }).click();
  const form = page.getByRole("form", { name: "Add configuration" });
  await form.getByLabel("Name").fill("2 BHK Classic");
  await form.getByLabel("BHK").fill("2");
  await form.getByLabel("Carpet area from (sq ft)").fill("980");
  await expect(form.getByText("91.0 sq m · auto")).toBeVisible();
  await form.getByLabel("Price from (₹)").fill("7800000");
  await expect(form.getByText("Shows as ₹ 78 L")).toBeVisible();
  await form.getByRole("button", { name: "Save" }).click();

  const row = page.getByRole("row", { name: /2 BHK Classic/ });
  await expect(row).toBeVisible();
  await expect(row.getByRole("cell", { name: "980" })).toBeVisible();
  await expect(row.getByText("91.0")).toBeVisible();
  await expect(row.getByText("₹ 78 L")).toBeVisible();
  await expect(
    page.locator("#publish-checklist").getByText("Add at least one configuration"),
  ).toHaveCount(0);
});

test("an admin adds towers and reorders them", async ({ page }) => {
  await page.goto(`${projectUrl}?tab=towers`);
  for (const name of ["Tower A", "Tower B"]) {
    await page.getByRole("button", { name: "+ Add tower" }).click();
    const form = page.getByRole("form", { name: "Add tower" });
    await form.getByLabel("Name").fill(name);
    await form.getByLabel("Floors").fill("22");
    await form.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("button", { name: `Edit ${name}` })).toBeVisible();
  }
  const list = page.getByRole("list", { name: "Towers and phases" });
  await expect(list.getByRole("listitem")).toHaveCount(2);

  await page.getByRole("button", { name: "Move Tower B up" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Tower B moved to position 1 of 2." }),
  ).toBeAttached();
  await expect(list.getByRole("listitem").first()).toContainText("Tower B");

  // Opening another tower while one has unsaved edits asks first; "Keep editing" keeps them.
  await page.getByRole("button", { name: "Edit Tower A" }).click();
  await page.getByRole("form", { name: "Edit Tower A" }).getByLabel("Floors").fill("24");
  await page.getByRole("button", { name: "Edit Tower B" }).click();
  const discard = page.getByRole("dialog", { name: "Discard your changes?" });
  await expect(discard).toBeVisible();
  await discard.getByRole("button", { name: "Keep editing" }).click();
  await expect(page.getByRole("form", { name: "Edit Tower A" }).getByLabel("Floors")).toHaveValue(
    "24",
  );
  await page
    .getByRole("form", { name: "Edit Tower A" })
    .getByRole("button", { name: "Cancel" })
    .click();

  // The new order was saved: it survives a reload.
  await page.reload();
  await expect(
    page.getByRole("list", { name: "Towers and phases" }).getByRole("listitem").first(),
  ).toContainText("Tower B");
});

test("an admin uploads photos and a PDF, orders them, pins the cover and hides one", async ({
  page,
}) => {
  await page.goto(`${projectUrl}?tab=media`);
  const panel = page.getByRole("tabpanel", { name: "Media", exact: true });
  const drop = panel.getByRole("button", { name: "Drag files here or browse" });
  await expect(panel.getByRole("radio", { name: "Photos · 0" })).toHaveAttribute(
    "aria-checked",
    "true",
  );

  // Two photos through the drop zone's button. First the honest label for the batch (nothing
  // pre-selected), then they are resized in the browser and sent with progress.
  await upload(page, drop, [
    samplePhoto("Tower-A-dusk.png"),
    samplePhoto("Clubhouse-lawn.png", 60),
  ]);
  const ask = page.getByRole("dialog", { name: "What are these 2 photos?" });
  await expect(ask.getByRole("radio", { name: /^Artist's impression/ })).toBeFocused();
  await ask.getByRole("button", { name: "Upload 2 photos" }).click();
  await expect(ask.getByText("Choose what these photos are.")).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
  await ask.getByRole("radio", { name: /^Artist's impression/ }).check();
  await ask.getByRole("button", { name: "Upload 2 photos" }).click();
  await expect(ask).toBeHidden();
  const photos = panel.getByRole("list", { name: "Photos in display order" });
  await expect(photos.getByRole("listitem")).toHaveCount(2);
  await expect(panel.getByRole("radio", { name: "Photos · 2" })).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Clubhouse-lawn.png was uploaded to Photos." }),
  ).toBeAttached();
  await expect(photos.getByRole("listitem").first()).toContainText("Tower A dusk");
  // Every image in the CMS has alt text: the title until alt text is written.
  await expect(photos.getByRole("img", { name: "Tower A dusk" })).toBeVisible();
  // Labelled on the way in, so both are shown on the website straight away.
  await expect(photos.getByText("Artist's impression")).toHaveCount(2);
  await expect(photos.getByRole("switch", { checked: true })).toHaveCount(2);

  // Reorder with the keyboard-friendly buttons; focus stays on the button that was used.
  await panel.getByRole("button", { name: "Move Clubhouse lawn up" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Clubhouse lawn moved to position 1 of 2." }),
  ).toBeAttached();
  await expect(photos.getByRole("listitem").first()).toContainText("Clubhouse lawn");
  await expect(panel.getByRole("button", { name: "Move Clubhouse lawn up" })).toBeFocused();

  // Two switches flipped in quick succession: the second waits its turn instead of being lost.
  await panel.getByRole("switch", { name: /^Show on website · Shown: Clubhouse lawn$/ }).click();
  await panel.getByRole("switch", { name: /^Show on website · Shown: Tower A dusk$/ }).click();
  await expect(panel.getByRole("switch", { name: /Clubhouse lawn$/ })).toHaveAttribute(
    "aria-checked",
    "false",
  );
  await expect(panel.getByRole("switch", { name: /Tower A dusk$/ })).toHaveAttribute(
    "aria-checked",
    "false",
  );
  await expect(panel.getByText("2 photos (0 shown)")).toBeVisible();
  await panel.getByRole("switch", { name: /^Show on website · Hidden: Tower A dusk$/ }).click();
  await expect(panel.getByRole("switch", { name: /Tower A dusk$/ })).toHaveAttribute(
    "aria-checked",
    "true",
  );

  // Pin the cover on the second photo.
  await panel.getByRole("button", { name: "Make Tower A dusk the cover photo" }).click();
  await expect(
    panel.getByRole("button", { name: "Cover photo, pinned: Tower A dusk" }),
  ).toHaveAttribute("aria-pressed", "true");

  // The first photo stays hidden: it stays in the CMS with a HIDDEN badge.
  await expect(photos.getByRole("listitem").first()).toContainText("HIDDEN");
  await expect(panel.getByText("2 photos (1 shown)")).toBeVisible();

  // Honest label and alt text.
  await panel.getByRole("button", { name: "Edit details: Tower A dusk" }).click();
  const details = page.getByRole("dialog", { name: "Photo details" });
  await details.getByLabel("Alt text").fill("SAMPLE tile standing in for Tower A at dusk");
  await details.getByLabel("Honest label").selectOption({ label: "Actual photo" });
  await details.getByRole("button", { name: "Save details" }).click();
  await expect(details).toBeHidden();
  await expect(
    photos.getByRole("img", { name: "SAMPLE tile standing in for Tower A at dusk" }),
  ).toBeVisible();
  await expect(photos.getByText("Actual photo")).toBeVisible();

  // A PDF dropped on the same zone goes to Documents (direct upload through the fake store),
  // with no label question. Its very long name is shortened for the API with the extension kept.
  await upload(page, drop, [samplePdf(`SAMPLE-specifications-${"x".repeat(230)}.pdf`)]);
  await expect(panel.getByRole("radio", { name: "Documents · 1" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  const documents = panel.getByRole("list", { name: "Documents in display order" });
  await expect(documents.getByRole("listitem")).toHaveCount(1);
  await expect(documents).toContainText("SAMPLE specifications");

  // A refused file is explained before anything is sent.
  await upload(page, drop, [
    { name: "logo.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg/>") },
  ]);
  await expect(panel.getByText(/SVG files can't be uploaded/)).toBeVisible();
  await panel.getByRole("button", { name: "Dismiss logo.svg" }).click();

  // The order, the cover and the hidden photo were saved: they survive a reload.
  await page.reload();
  await page.getByRole("tab", { name: "Media", exact: true }).click();
  const reloaded = page.getByRole("list", { name: "Photos in display order" });
  await expect(reloaded.getByRole("listitem").first()).toContainText("Clubhouse lawn");
  await expect(reloaded.getByRole("listitem").first()).toContainText("HIDDEN");
  await expect(
    page.getByRole("button", { name: "Cover photo, pinned: Tower A dusk" }),
  ).toBeVisible();
});

test("an admin picks the share image from the project's photos", async ({ page }) => {
  await page.goto(`${projectUrl}?tab=seo`);
  const seo = page.getByRole("tabpanel", { name: "SEO", exact: true });
  await expect(seo.getByText("No share image chosen.")).toBeVisible();
  const choices = seo.getByRole("group", { name: "Choose from this project's photos" });
  // The radio is visually hidden; the photo is its visible label, as people use it.
  await choices.getByRole("img", { name: "SAMPLE tile standing in for Tower A at dusk" }).click();
  await expect(
    choices.getByRole("radio", { name: "SAMPLE tile standing in for Tower A at dusk" }),
  ).toBeChecked();
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();

  // Saved as seo.og_image_id: after a reload the photo is still chosen and previewed.
  await page.reload();
  const again = page
    .getByRole("tabpanel", { name: "SEO", exact: true })
    .getByRole("group", { name: "Choose from this project's photos" });
  await expect(
    again.getByRole("radio", { name: "SAMPLE tile standing in for Tower A at dusk" }),
  ).toBeChecked();
  await expect(page.getByText("No share image chosen.")).toHaveCount(0);
});

test("an admin adds a floor plan to a configuration", async ({ page }) => {
  await page.goto(`${projectUrl}?tab=configurations`);
  await upload(page, page.getByRole("button", { name: "Add floor plan for 2 BHK Classic" }), [
    samplePhoto("2BHK-plan.png", 90),
  ]);
  await expect(
    page.getByRole("button", { name: "Replace floor plan for 2 BHK Classic" }),
  ).toBeVisible();
  await expect(page.getByRole("row", { name: /2 BHK Classic/ }).getByRole("img")).toBeVisible();
  // Plans are line drawings: encoded lossless in the browser (WebP in Chromium).
  const projectId = projectUrl.split("/").pop();
  const saved = await apiCall(page, "GET", `/api/v1/admin/projects/${projectId}`);
  const { configurations } = (await saved.json()) as {
    configurations: { floor_plans: { format: string }[] }[];
  };
  expect(configurations[0]?.floor_plans[0]?.format).toBe("webp");
});

test("an admin uploads the RERA QR code, publishes the project and unpublishes it", async ({
  page,
}) => {
  await page.goto(`${projectUrl}?tab=documents`);
  const checklist = page.locator("#publish-checklist");
  await expect(checklist.getByText("RERA QR code missing")).toBeVisible();
  await expect(page.getByText("RERA QR code image · missing")).toBeVisible();

  await upload(page, page.getByRole("button", { name: "Upload QR image" }), [sampleQr()]);
  await expect(page.getByText("RERA QR code image · uploaded")).toBeVisible();
  await expect(checklist.getByText("Nothing is blocking publishing.")).toBeVisible();

  // Publishing works now that the QR is there.
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Published. The project is live." }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Published", level: 2 })).toBeVisible();

  // COMPLIANCE: a live project's QR can be replaced, never removed or hidden (the API refuses
  // both with 409; apps/api tests cover that). The panel offers only Replace.
  await expect(page.getByRole("button", { name: "Replace QR image" })).toBeVisible();
  await expect(
    page.getByText(/can't be removed or hidden while the project is published/),
  ).toBeVisible();
  const projectId = projectUrl.split("/").pop();
  const live = await apiCall(page, "GET", `/api/v1/admin/projects/${projectId}`);
  const body = (await live.json()) as {
    publish_state: string;
    publish_blockers: string[];
    rera: { qr: { kind: string; format: string } | null };
  };
  expect(body.publish_state).toBe("published");
  expect(body.publish_blockers).toEqual([]);
  expect(body.rera.qr?.kind).toBe("image");
  // The QR is uploaded lossless (PNG), so it stays sharp enough to scan.
  expect(body.rera.qr?.format).toBe("png");

  await page.getByRole("button", { name: "Unpublish" }).click();
  const dialog = page.getByRole("dialog", { name: "Unpublish this project?" });
  await dialog.getByRole("button", { name: "Unpublish" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("status").filter({ hasText: "Unpublished." })).toBeVisible();
});

test("an admin archives the project", async ({ page }) => {
  await page.goto(projectUrl);
  await page.getByRole("button", { name: "Archive project" }).click();
  const dialog = page.getByRole("dialog", { name: "Archive this project?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  await dialog.getByRole("button", { name: "Archive project" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("status").filter({ hasText: "Archived." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Archived", level: 2 })).toBeVisible();

  // The list shows it with its publishing state and can be filtered to archived projects.
  await page.goto(`/admin/projects?publish_state=archived&q=${encodeURIComponent(projectName)}`);
  const row = page.getByRole("row", { name: new RegExp(projectName) });
  await expect(row).toBeVisible();
  await expect(row.getByText("Archived")).toBeVisible();
  await expect(row.getByText(cityName)).toBeVisible();
});

test("sample projects carry the SAMPLE badge and banner", async ({ page }) => {
  await page.goto("/admin/projects?q=sample-project");
  const row = page.getByRole("row", { name: /Sample — Project A/ });
  await expect(row.getByText("SAMPLE", { exact: true })).toBeVisible();
  await row.getByRole("link", { name: "Sample — Project A" }).click();
  await expect(
    page
      .getByRole("note")
      .filter({ hasText: "Sample data · nothing here is shown on the live site" }),
  ).toBeVisible();
  // Sample rows use placeholder RERA numbers and stay drafts.
  await expect(page.getByText(/UPRERAPRJ-SAMPLE-01/).first()).toBeVisible();
  await expect(page.locator("#publish-checklist").getByText("RERA QR code missing")).toBeVisible();
});

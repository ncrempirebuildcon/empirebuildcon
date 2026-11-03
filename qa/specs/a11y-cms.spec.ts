// Accessibility of the CMS project screens: axe finds no serious or critical WCAG 2.1 A/AA issues
// on the projects list, every tab of the project editor, the create form, the catalogue, the
// Media tab with its details dialog, and the media library in both views (DESIGN_SYSTEM.md §9).
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE, apiCall, apiUpload, runId, seriousA11yViolations } from "../lib/auth";
import { samplePhoto } from "../lib/files";

// Signed in once by auth.setup.ts (the API limits sign-ins per network).
test.use({ storageState: CMS_STATE });

test("the projects list has no serious accessibility violations", async ({ page }) => {
  await page.goto("/admin/projects");
  await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Projects" })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
});

test("the new project form has no serious accessibility violations", async ({ page }) => {
  await page.goto("/admin/projects/new");
  await expect(page.getByLabel("Project name")).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
});

test("the catalogue has no serious accessibility violations", async ({ page }) => {
  await page.goto("/admin/catalogue");
  await expect(page.getByRole("heading", { level: 2, name: "Amenities" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Cities" })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);

  // With an add form open too.
  await page.getByRole("button", { name: "+ Add amenity" }).click();
  await expect(page.getByRole("form", { name: "Add amenity" })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
});

test("every tab of the project editor has no serious accessibility violations", async ({
  page,
}) => {
  // WHY a longer timeout: axe runs on every one of the ~11 tabs. That takes about 26 s locally
  // and went past the default 30 s on CI once the suite had more specs (task 5.3), with nothing
  // failing. Only the time limit changes; every check stays.
  test.setTimeout(90_000);
  // The sample project has towers, configurations, plans and the rest, so every tab has content.
  await page.goto("/admin/projects?q=sample-project-a");
  await page.getByRole("link", { name: "Sample — Project A" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Sample — Project A" })).toBeVisible();
  await expect(
    page
      .getByRole("note")
      .filter({ hasText: "Sample data · nothing here is shown on the live site" }),
  ).toBeVisible();
  const tabs = await page.getByRole("tab").allTextContents();
  expect(tabs.length).toBeGreaterThan(8);
  for (const name of tabs) {
    await page.getByRole("tab", { name, exact: true }).click();
    await expect(page.getByRole("tabpanel", { name, exact: true })).toBeVisible();
    expect(await seriousA11yViolations(page), `tab ${name}`).toEqual([]);
  }
});

test("an empty draft's editor, its forms and the delete dialog are accessible", async ({
  page,
}) => {
  const created = await apiCall(page, "POST", "/api/v1/admin/projects", {
    name: `E2E A11y ${runId()}`,
    status: "upcoming",
  });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  const tower = await apiCall(page, "POST", `/api/v1/admin/projects/${id}/towers`, {
    name: "Tower A",
    kind: "tower",
  });
  expect(tower.status()).toBe(201);

  await page.goto(`/admin/projects/${id}?tab=towers`);
  await expect(page.getByRole("tablist", { name: "Project sections" })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);

  // Add forms open inline; they are accessible too.
  await page.getByRole("tab", { name: "Configurations", exact: true }).click();
  await page.getByRole("button", { name: "+ Add configuration" }).click();
  await expect(page.getByRole("form", { name: "Add configuration" })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
  await page
    .getByRole("form", { name: "Add configuration" })
    .getByRole("button", { name: "Cancel" })
    .click();

  await page.getByRole("tab", { name: "Payment plans", exact: true }).click();
  await page.getByRole("button", { name: "+ Add payment plan" }).click();
  await expect(page.getByRole("form", { name: "Add payment plan" })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
  await page
    .getByRole("form", { name: "Add payment plan" })
    .getByRole("button", { name: "Cancel" })
    .click();

  // A confirm dialog is accessible too, and is a real dialog (not the browser's confirm()).
  await page.getByRole("button", { name: "Delete draft" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete this draft?" });
  await expect(dialog).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
  await dialog.getByRole("button", { name: "Delete project" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "The project was deleted." }),
  ).toBeVisible();
  // The one-off notice is dropped from the address, so a reload doesn't repeat it.
  await expect(page).toHaveURL(/\/admin\/projects$/);
});

/** A draft with one photo and one PDF attached, made through the API (no UI clicks). */
async function projectWithMedia(page: Page): Promise<string> {
  const created = await apiCall(page, "POST", "/api/v1/admin/projects", {
    name: `E2E Media A11y ${runId()}`,
    status: "upcoming",
  });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  const photo = await apiUpload(page, "/api/v1/admin/media/images", {
    file: samplePhoto("A11y-photo.png"),
    title: "A11y photo",
    attach_to: `project:${id}`,
    role: "gallery",
  });
  expect(photo.status()).toBe(201);
  return id;
}

test("the Media tab and its details dialog have no serious accessibility violations", async ({
  page,
}) => {
  const id = await projectWithMedia(page);
  await page.goto(`/admin/projects/${id}?tab=media`);
  const panel = page.getByRole("tabpanel", { name: "Media", exact: true });
  await expect(panel.getByRole("list", { name: "Photos in display order" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Drag files here or browse" })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);

  // The other two lists, and the details dialog.
  await panel.getByRole("radio", { name: /Videos/ }).click();
  expect(await seriousA11yViolations(page)).toEqual([]);
  await panel.getByRole("radio", { name: /Documents/ }).click();
  expect(await seriousA11yViolations(page)).toEqual([]);
  await panel.getByRole("radio", { name: /Photos/ }).click();

  // COMPLIANCE: a photo uploaded without an honest label stays hidden; its switch says why and
  // offers a shortcut to label it.
  await expect(panel.getByText("Hidden until labelled")).toBeVisible();
  const toggle = panel.getByRole("switch", { name: /A11y photo$/ });
  await expect(toggle).toHaveAttribute("aria-disabled", "true");
  await expect(toggle).toHaveAccessibleDescription(
    "Add an honest label to show it on the website.",
  );
  expect(await seriousA11yViolations(page)).toEqual([]);

  await panel.getByRole("button", { name: "Add label: A11y photo" }).click();
  const dialog = page.getByRole("dialog", { name: "Photo details" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Honest label").selectOption({ label: "Progress photo" });
  await expect(dialog.getByLabel("Month", { exact: true })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
  await dialog.getByRole("button", { name: "Save details" }).click();
  await expect(dialog.getByText("Choose the month the photo was taken.")).toBeVisible();
  await dialog.getByLabel("Month", { exact: true }).selectOption({ label: "January" });
  await dialog.getByLabel("Year").selectOption({ index: 1 });
  await dialog.getByRole("button", { name: "Save details" }).click();
  await expect(dialog).toBeHidden();

  // Labelled now, so it can be shown.
  await expect(panel.getByText(/^Progress photo · Jan \d{4}$/)).toBeVisible();
  await expect(toggle).not.toHaveAttribute("aria-disabled", "true");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");

  // The Documents tab with its QR and brochure panels, and a refused upload in the queue.
  await page.getByRole("tab", { name: "Documents", exact: true }).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Upload brochure (PDF)" }).click();
  await (await chooser).setFiles(samplePhoto("not-a-brochure.png"));
  await expect(page.getByText("not-a-brochure.png: the brochure must be a PDF.")).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
});

test("the media library has no serious accessibility violations, as a grid and a list", async ({
  page,
}) => {
  await projectWithMedia(page);
  // An unattached photo too, so the library shows an enabled "Delete from library".
  const loose = await apiUpload(page, "/api/v1/admin/media/images", {
    file: samplePhoto("A11y-unattached.png", 30),
    title: `A11y unattached ${runId()}`,
  });
  expect(loose.status()).toBe(201);

  await page.goto("/admin/media");
  await expect(page.getByRole("heading", { level: 1, name: "Media" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Media files" })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);

  await page.getByRole("radio", { name: "List" }).click();
  await expect(page).toHaveURL(/view=list/);
  await expect(page.getByRole("table", { name: "Media files" })).toBeVisible();
  expect(await seriousA11yViolations(page)).toEqual([]);
});

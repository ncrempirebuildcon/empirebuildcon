// Accessibility of the CMS project screens: axe finds no serious or critical WCAG 2.1 A/AA issues
// on the projects list, every tab of the project editor, the create form and the catalogue
// (handbook/DESIGN_SYSTEM.md §9).
import { expect, test } from "@playwright/test";
import { CMS_STATE, apiCall, runId, seriousA11yViolations } from "../lib/auth";

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

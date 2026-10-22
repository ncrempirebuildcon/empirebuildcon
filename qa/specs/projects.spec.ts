// CMS projects journey (spec Phase 4 part 1): catalogue city and locality → new project →
// location → configuration with area and price → publish blockers → tower order → archive.
import { expect, test, type Page } from "@playwright/test";
import { CMS_STATE, apiCall, runId } from "../lib/auth";

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

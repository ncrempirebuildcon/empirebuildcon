// Media library journey (spec Phase 4 part 2 §2): search in the address, rename and alt text in the
// details dialog, delete only when the file is attached to nothing (with a confirm dialog), the
// list view, and the Media menu item. Files come from lib/files.ts and go to the API's fake store.
import { expect, test } from "@playwright/test";
import { CMS_STATE, apiCall, apiUpload, runId } from "../lib/auth";
import { samplePhoto } from "../lib/files";

// Signed in once by auth.setup.ts (the API limits sign-ins per network).
test.use({ storageState: CMS_STATE });

test("an admin renames and deletes an unattached file, and can't delete an attached one", async ({
  page,
}) => {
  const id = runId();
  const loose = await apiUpload(page, "/api/v1/admin/media/images", {
    file: samplePhoto("loose.png", 20),
    title: `E2E loose ${id}`,
  });
  expect(loose.status()).toBe(201);
  const project = await apiCall(page, "POST", "/api/v1/admin/projects", {
    name: `E2E Library ${id}`,
    status: "upcoming",
  });
  expect(project.status()).toBe(201);
  const { id: projectId } = (await project.json()) as { id: string };
  const attached = await apiUpload(page, "/api/v1/admin/media/images", {
    file: samplePhoto("attached.png", 50),
    title: `E2E attached ${id}`,
    attach_to: `project:${projectId}`,
    role: "gallery",
  });
  expect(attached.status()).toBe(201);

  // The menu item is a link now.
  await page.goto("/admin");
  await page
    .getByRole("navigation", { name: "Sections" })
    .getByRole("link", { name: "Media" })
    .click();
  await expect(page).toHaveURL(/\/admin\/media$/);

  // Search lives in the address.
  await page.getByLabel("Search").fill(`E2E loose ${id}`);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page).toHaveURL(new RegExp(`q=E2E\\+loose\\+${id}`));
  const files = page.getByRole("list", { name: "Media files" });
  await expect(files.getByRole("listitem")).toHaveCount(1);
  await expect(files).toContainText("Not attached to anything");

  // Rename (keeping the searched words, so it stays in this filtered view) and alt text.
  await page.getByRole("button", { name: `Edit details: E2E loose ${id}` }).click();
  const details = page.getByRole("dialog", { name: "Photo details" });
  await details.getByLabel("Title").fill(`E2E loose ${id} renamed`);
  await details.getByLabel("Alt text").fill("SAMPLE gradient tile");
  await details.getByLabel("Honest label").selectOption({ label: "Actual photo" });
  await details.getByRole("button", { name: "Save details" }).click();
  await expect(details).toBeHidden();
  await expect(files.getByRole("img", { name: "SAMPLE gradient tile" })).toBeVisible();
  await expect(files.getByRole("heading", { name: `E2E loose ${id} renamed` })).toBeVisible();
  await expect(files.getByText("Actual photo")).toBeVisible();

  // Delete asks first; Cancel has focus; afterwards focus returns to the search field.
  await page.getByRole("button", { name: `Delete from library: E2E loose ${id} renamed` }).click();
  const dialog = page.getByRole("dialog", {
    name: `Delete E2E loose ${id} renamed from the library?`,
  });
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  await dialog.getByRole("button", { name: "Delete from library" }).click();
  await expect(dialog).toBeHidden();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: `E2E loose ${id} renamed was deleted from the library.` }),
  ).toBeAttached();
  await expect(page.getByLabel("Search")).toBeFocused();

  // A file still attached somewhere isn't offered for deletion (the list says where it is used),
  // and the API refuses it too.
  await page.goto(`/admin/media?q=${encodeURIComponent(`E2E attached ${id}`)}&view=list`);
  const row = page.getByRole("row", { name: new RegExp(`E2E attached ${id}`) });
  await expect(row.getByText("Attached in 1 place")).toBeVisible();
  await expect(row.getByRole("button", { name: /^Edit details/ })).toBeVisible();
  await expect(row.getByRole("button", { name: /^Delete from library/ })).toHaveCount(0);
  const { id: mediaId } = (await attached.json()) as { id: string };
  const refused = await apiCall(page, "DELETE", `/api/v1/admin/media/${mediaId}`);
  expect(refused.status()).toBe(409);

  // "Only files not attached to anything" is a filter in the address too.
  await page.getByLabel("Only files not attached to anything").check();
  await expect(page).toHaveURL(/unattached=true/);
  await expect(page.getByText("No files match these filters.")).toBeVisible();
});

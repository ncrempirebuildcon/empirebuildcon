/**
 * Chat widget launch state guard (Phase 7 Task 7.3).
 *
 * Implements:
 * - With chat_widget flag off by default (as at launch), verifies:
 *   - / has no "Ask about our projects" launcher button.
 *   - /projects has no "Ask about our projects" launcher button.
 *   - A project detail page has no launcher button.
 *   - No lazy-loaded chat panel code/chunk is fetched.
 */
import { expect, test } from "@playwright/test";
import { CMS_STATE } from "../lib/auth";
import { catalogueProject } from "../lib/catalogue";

test.use({ storageState: CMS_STATE });

test.describe("Chat Widget launch guard (Task 7.3)", () => {
  test("with chat_widget flag off, the launcher button is absent and no chat panel chunk is requested", async ({
    page,
  }) => {
    let chatPanelChunkRequested = false;
    page.on("request", (req) => {
      const url = req.url();
      if (url.includes("ChatPanel")) {
        chatPanelChunkRequested = true;
      }
    });

    // 1. Home page (/)
    const homeRes = await page.goto("/");
    expect(homeRes?.status()).toBe(200);
    await expect(page.getByRole("button", { name: /ask about our projects/i })).toHaveCount(0);

    // 2. Projects list (/projects)
    const projectsRes = await page.goto("/projects");
    expect(projectsRes?.status()).toBe(200);
    await expect(page.getByRole("button", { name: /ask about our projects/i })).toHaveCount(0);

    // 3. Project detail page
    const project = await catalogueProject(page);
    const detailRes = await page.goto(`/projects/${project.slug}`);
    expect(detailRes?.status()).toBe(200);
    await expect(page.getByRole("button", { name: /ask about our projects/i })).toHaveCount(0);

    expect(chatPanelChunkRequested).toBe(false);
  });
});

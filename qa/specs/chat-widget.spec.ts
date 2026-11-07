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
    const jsBodies: Array<{ url: string; text: string }> = [];
    page.on("response", async (res) => {
      const ct = res.headers()["content-type"] || "";
      if (ct.includes("javascript")) {
        try {
          const text = await res.text();
          jsBodies.push({ url: res.url(), text });
        } catch {
          // Ignore aborted or closed responses
        }
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

    // M2: verify none of the loaded JavaScript bundles contain chat-panel-specific strings
    const hasChatPanelCode = jsBodies.some((body) => body.text.includes("resting for today"));
    expect(hasChatPanelCode).toBe(false);
  });
});

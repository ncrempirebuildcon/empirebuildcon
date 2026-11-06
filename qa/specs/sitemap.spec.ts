/**
 * Browser journeys for sitemap.xml and robots.txt (task 5.6b, D-046).
 *
 * Implements ARCHITECTURE §16 (SEO):
 *   - /sitemap.xml is valid XML (parses without parsererror).
 *   - /sitemap.xml contains a project published through catalogueProject.
 *   - After unpublishing the project through the staff API and draining the outbox,
 *     the project is gone from /sitemap.xml.
 *   - /robots.txt says Disallow: / in the test environment and includes the Sitemap: directive.
 *
 * Collaborators: Antigravity <noreply@google.com>. Decisions: D-046, D-047.
 */
import { expect, test } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";
import { catalogueProject, drainOutbox } from "../lib/catalogue";

test.use({ storageState: CMS_STATE });

test.describe("Sitemap and Robots (Task 5.6b)", () => {
  test("/sitemap.xml is valid XML, includes published project, and drops it after unpublish and outbox drain", async ({
    page,
  }) => {
    // 1. Create and publish a project through the catalogue helper
    const project = await catalogueProject(page);
    await drainOutbox(page);

    // 2. Fetch /sitemap.xml and verify it is valid XML
    const sitemapRes = await page.goto("/sitemap.xml");
    expect(sitemapRes?.status()).toBe(200);
    const contentType = sitemapRes?.headers()["content-type"] ?? "";
    expect(contentType).toMatch(/xml/);

    const xmlText = (await sitemapRes?.text()) ?? "";
    expect(xmlText).toContain("<urlset");
    expect(xmlText).toContain("</urlset>");

    // Verify XML well-formedness using DOMParser
    const isValidXml = await page.evaluate((xml) => {
      const doc = new DOMParser().parseFromString(xml, "application/xml");
      return !doc.querySelector("parsererror");
    }, xmlText);
    expect(isValidXml).toBe(true);

    // 3. Verify the published project is present in the sitemap
    expect(xmlText).toContain(`/projects/${project.slug}`);

    // Verify core list pages are also present
    expect(xmlText).toMatch(/<loc>https?:\/\/[^/]+\/<\/loc>/);
    expect(xmlText).toMatch(/<loc>https?:\/\/[^/]+\/projects<\/loc>/);
    expect(xmlText).toMatch(/<loc>https?:\/\/[^/]+\/properties<\/loc>/);
    expect(xmlText).toMatch(/<loc>https?:\/\/[^/]+\/contact<\/loc>/);
    expect(xmlText).toMatch(/<loc>https?:\/\/[^/]+\/blog<\/loc>/);

    // 4. Unpublish the project via staff API
    const unpubRes = await apiCall(page, "POST", `/api/v1/admin/projects/${project.id}/unpublish`);
    expect(unpubRes.status()).toBe(200);

    // Drain the outbox to trigger cache tag revalidation (retrying on transient 429)
    await expect
      .poll(
        async () => {
          try {
            await drainOutbox(page);
            return true;
          } catch {
            return false;
          }
        },
        { timeout: 5000, intervals: [500, 1000] },
      )
      .toBe(true);

    // 5. Verify the project is gone from /sitemap.xml
    await expect
      .poll(
        async () => {
          const res = await page.goto("/sitemap.xml");
          const text = (await res?.text()) ?? "";
          return text.includes(`/projects/${project.slug}`);
        },
        { timeout: 15_000, intervals: [500, 1000, 2000] },
      )
      .toBe(false);
  });

  test("/robots.txt blocks crawling by default in the test environment and declares the sitemap", async ({
    page,
  }) => {
    const res = await page.goto("/robots.txt");
    expect(res?.status()).toBe(200);
    const text = (await res?.text()) ?? "";

    // In test environment, ALLOW_INDEXING is not active, so crawling is disallowed
    expect(text).toMatch(/^User-Agent:\s*\*/im);
    expect(text).toMatch(/^Disallow:\s*\//im);
    expect(text).not.toMatch(/^Allow:\s*\//im);

    // Sitemap line points to sitemap.xml on canonical URL
    expect(text).toMatch(/^Sitemap:\s*https?:\/\/[^/]+\/sitemap\.xml/im);
  });
});

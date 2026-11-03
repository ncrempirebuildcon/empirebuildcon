/**
 * The public site's accessibility and 390 px pass (task 5.7, D-049): every public route, at a
 * phone's 390 px and on a desktop, with
 *   - axe (WCAG 2.0/2.1/2.2 A and AA): no serious or critical violation;
 *   - no sideways scroll at 390 px;
 *   - every button, form control and stand-alone link at least 44×44 px (DESIGN_SYSTEM touch
 *     targets); links inside running text are exempt, as WCAG 2.5.8 allows;
 *   - the enforced CSP: no violation;
 *   - one h1, a skip link that moves focus to the main content, and visible keyboard focus.
 *
 * No sign-ins beyond the shared CMS session (to find a published project), no submissions.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";
import { catalogueProject } from "../lib/catalogue";
import { draftPage } from "../lib/content";

test.use({ storageState: CMS_STATE });

const VIEWPORTS = [
  { name: "390 px", width: 390, height: 844 },
  { name: "desktop", width: 1280, height: 900 },
] as const;

async function publishedPage(page: Page, kind: "standard" | "legal"): Promise<string> {
  const made = await draftPage(page, kind);
  const blocks = await apiCall(page, "PUT", `/api/v1/admin/pages/${made.id}/blocks`, {
    blocks: [
      { type: "rich_text", data: { heading: "Section", body: "Some *text*, a [link](/contact)." } },
    ],
  });
  expect(blocks.status(), await blocks.text()).toBe(200);
  const published = await apiCall(page, "POST", `/api/v1/admin/pages/${made.id}/publish`);
  expect(published.status(), await published.text()).toBe(200);
  return `/${made.slug}`;
}

async function routes(page: Page): Promise<string[]> {
  const project = await catalogueProject(page);
  const standard = await publishedPage(page, "standard");
  const legal = await publishedPage(page, "legal");
  return [
    "/",
    "/projects",
    "/projects?city=sample-city&sort=price_asc",
    "/properties",
    `/projects/${project.slug}`,
    `/projects/${project.slug}/${project.configSlugs[0]}`,
    "/cities/sample-city",
    "/contact",
    standard,
    legal,
    "/e2e-no-such-page",
  ];
}

/** Interactive elements under 44×44 px that are not links inside running text. */
async function smallTargets(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const found: string[] = [];
    const nodes = document.querySelectorAll<HTMLElement>(
      "a[href], button, input:not([type=hidden]), select, textarea, summary",
    );
    for (const el of nodes) {
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (box.width === 0 || box.height === 0 || style.visibility === "hidden") continue;
      if (el.closest(".sr-only") || el.classList.contains("sr-only")) continue;
      // The skip link is off screen until focused.
      if (box.bottom < 0 || box.right < 0) continue;
      // WCAG 2.5.8 exception: a link inside a sentence (its parent holds other text).
      if (el.tagName === "A" && style.display === "inline") {
        const parentText = el.parentElement?.textContent?.trim() ?? "";
        const ownText = el.textContent?.trim() ?? "";
        if (parentText.length > ownText.length) continue;
      }
      // Checkboxes and radios count their label (the label is the target).
      if (el instanceof HTMLInputElement && ["checkbox", "radio"].includes(el.type)) {
        const label = el.closest("label") ?? document.querySelector(`label[for="${el.id}"]`);
        const lb = label?.getBoundingClientRect();
        if (lb && lb.height >= 43.5 && lb.width >= 43.5) continue;
      }
      if (box.width < 43.5 || box.height < 43.5) {
        const name = (el.getAttribute("aria-label") ?? el.textContent ?? el.tagName).trim();
        found.push(
          `${el.tagName.toLowerCase()} "${name.slice(0, 40)}" ${Math.round(box.width)}×${Math.round(box.height)}`,
        );
      }
    }
    return found;
  });
}

for (const viewport of VIEWPORTS) {
  test(`every public route passes at ${viewport.name}`, async ({ browser, page }) => {
    test.setTimeout(180_000);
    const paths = await routes(page);
    const visitorContext = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
    });
    const visitor = await visitorContext.newPage();
    const csp: string[] = [];
    visitor.on("console", (msg) => {
      if (/Content Security Policy|violates the following/.test(msg.text())) csp.push(msg.text());
    });
    const problems: string[] = [];
    for (const path of paths) {
      await visitor.goto(path);
      await expect(visitor.locator("#main-content")).toBeVisible();
      const axe = await new AxeBuilder({ page: visitor })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      for (const v of axe.violations) {
        if (v.impact === "serious" || v.impact === "critical") {
          problems.push(`${path}: axe ${v.id} (${v.nodes.length})`);
        }
      }
      const overflow = await visitor.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      if (overflow > 0) problems.push(`${path}: ${overflow}px sideways scroll`);
      for (const small of await smallTargets(visitor)) problems.push(`${path}: small ${small}`);
      const h1 = await visitor.getByRole("heading", { level: 1 }).count();
      if (h1 !== 1) problems.push(`${path}: ${h1} h1`);
    }
    expect(problems, problems.join("\n")).toEqual([]);
    expect(csp).toEqual([]);
    await visitorContext.close();
  });
}

test("the skip link moves focus to the main content, with a visible focus ring", async ({
  browser,
}) => {
  const visitorContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const visitor = await visitorContext.newPage();
  await visitor.goto("/projects");
  await visitor.keyboard.press("Tab");
  const skip = visitor.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await visitor.keyboard.press("Enter");
  await expect(visitor).toHaveURL(/#main-content$/);
  // The next Tab lands inside the main content, not back in the header.
  await visitor.keyboard.press("Tab");
  const insideMain = await visitor.evaluate(
    () => document.getElementById("main-content")?.contains(document.activeElement) ?? false,
  );
  expect(insideMain).toBe(true);
  const ring = await visitor.evaluate(() => {
    const s = getComputedStyle(document.activeElement as Element);
    return `${s.outlineStyle} ${s.outlineWidth} ${s.boxShadow}`;
  });
  expect(ring, "a visible focus ring").not.toMatch(/^none 0px none$/);
  await visitorContext.close();
});

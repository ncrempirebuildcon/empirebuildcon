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

/**
 * Checkbox labels whose tap area reaches over a neighbour: a tap just above or below a label
 * must not land on it (a consent box must never be ticked by a tap meant for something else).
 */
async function overreachingLabels(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const found: string[] = [];
    for (const input of document.querySelectorAll<HTMLInputElement>("input[type=checkbox]")) {
      const label = input.labels?.[0];
      if (!label) continue;
      // Measured on screen: elementFromPoint sees nothing outside the viewport.
      label.scrollIntoView({ block: "center" });
      const box = label.getBoundingClientRect();
      if (box.height === 0) continue;
      // Anything else on screen whose box meets the label's: a tap in the shared strip must
      // reach that element, not the label.
      const others = document.querySelectorAll<HTMLElement>(
        "a, button, summary, input, textarea, select, label, p, li, span",
      );
      for (const other of others ?? []) {
        if (other === input || label.contains(other) || other.contains(label)) continue;
        // Text inside a closed <details> keeps a layout box but isn't shown.
        if (!other.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true }))
          continue;
        const o = other.getBoundingClientRect();
        const top = Math.max(box.top, o.top);
        const bottom = Math.min(box.bottom, o.bottom);
        const left = Math.max(box.left, o.left);
        const right = Math.min(box.right, o.right);
        if (bottom - top < 1 || right - left < 1) continue;
        const x = (left + right) / 2;
        const y = (top + bottom) / 2;
        if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) {
          found.push(`label "${(label.textContent ?? "").trim().slice(0, 30)}" not measurable`);
          continue;
        }
        const hit = document.elementFromPoint(x, y);
        if (hit && label.contains(hit) && !other.contains(hit)) {
          const name = (label.textContent ?? "").trim().slice(0, 30);
          const what = (other.textContent ?? other.tagName).trim().slice(0, 30);
          found.push(`label "${name}" covers "${what}"`);
        }
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
      // WHY: Next.js streams some metadata (the 404 page's title) after the body, so axe could
      // run a moment before the <title> exists (flaky document-title, 7 Nov 2026).
      await expect(visitor).toHaveTitle(/\S/);
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
      // Labels are checked with every
      // disclosure open (an open consent text sits right above the marketing box).
      await visitor.evaluate(() => {
        for (const d of document.querySelectorAll("details")) d.open = true;
      });
      for (const over of await overreachingLabels(visitor)) problems.push(`${path}: ${over}`);
      const h1 = await visitor.getByRole("heading", { level: 1 }).count();
      if (h1 !== 1) problems.push(`${path}: ${h1} h1`);
    }
    expect(problems, problems.join("\n")).toEqual([]);
    expect(csp).toEqual([]);
    await visitorContext.close();
  });
}

test("the label check finds a label that reaches over its neighbour", async ({ page }) => {
  // Negative control for overreachingLabels: two rows 8 px apart, labels padded 12 px into them.
  await page.setContent(`
    <form style="display:grid;gap:8px;font:14px/20px sans-serif">
      <div style="display:flex"><input id="a" type="checkbox"><label for="a" style="margin:-12px 0;padding:12px 0">First</label></div>
      <div style="display:flex"><input id="b" type="checkbox"><label for="b" style="margin:-12px 0;padding:12px 0">Second</label></div>
    </form>`);
  expect((await overreachingLabels(page)).length).toBeGreaterThan(0);
  await page.setContent(`
    <form style="display:grid;gap:8px;font:14px/20px sans-serif">
      <div style="display:flex"><input id="a" type="checkbox"><label for="a" style="padding:12px 0">First</label></div>
      <div style="display:flex"><input id="b" type="checkbox"><label for="b" style="padding:12px 0">Second</label></div>
    </form>`);
  expect(await overreachingLabels(page)).toEqual([]);
});

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
  // The next Tab lands inside the main content, not back in the header, and the sticky header
  // doesn't cover it (WCAG 2.4.11).
  await visitor.keyboard.press("Tab");
  const focus = await visitor.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    const box = el.getBoundingClientRect();
    const header = document.querySelector("header")?.getBoundingClientRect();
    return {
      insideMain: document.getElementById("main-content")?.contains(el) ?? false,
      top: box.top,
      headerBottom: header ? header.bottom : 0,
    };
  });
  expect(focus.insideMain).toBe(true);
  expect(focus.top, "focused element below the sticky header").toBeGreaterThanOrEqual(
    focus.headerBottom,
  );
  const ring = await visitor.evaluate(() => {
    const s = getComputedStyle(document.activeElement as Element);
    return `${s.outlineStyle} ${s.outlineWidth} ${s.boxShadow}`;
  });
  expect(ring, "a visible focus ring").not.toMatch(/^none 0px none$/);
  await visitorContext.close();
});

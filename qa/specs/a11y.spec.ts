// Accessibility: axe finds no serious or critical WCAG 2.1 A/AA issues (DESIGN_SYSTEM §9).
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const pages = [
  { name: "home", path: "/" },
  { name: "staff sign-in", path: "/admin/login" },
  { name: "404", path: "/this-page-does-not-exist" },
];

for (const { name, path } of pages) {
  test(`${name} has no serious accessibility violations`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });
}

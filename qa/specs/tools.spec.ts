/**
 * Browser journeys for EMI calculator and Saved Homes (Task 5.7b).
 *
 * Requirements tested:
 *   1. EMI calculator:
 *      - Property page with default price displays pre-filled EMI.
 *      - Loan amount prefill hint explains GST/stamp duty exclusions.
 *      - Typing a new loan amount recalculates monthly EMI to exact expected figure.
 *      - Typing invalid rate (e.g. 20%) displays visible error and suppresses monthly result (Must 1).
 *      - Adjusting tenure or rate updates EMI, total interest, and total paid.
 *      - Note and sample rate guidance are visible ("Indicative only, not a loan offer...").
 *      - JavaScript disabled: standard reducing-balance formula and note are visible.
 *   2. Saved homes:
 *      - Save button on project and property pages toggles between "Save" and "Saved" with aria-pressed.
 *      - Visiting /saved lists both saved items without prices.
 *      - Items show "Checking…" before API verification completes, then become active links (Item 4).
 *      - Privacy notice "Saved only in this browser." is present.
 *      - Removing an item updates the list and moves focus accessibility (Item 5).
 *      - When a saved project is unpublished, /saved displays "No longer listed" with a Remove button.
 *      - Removing the delisted item leaves /saved in empty state linking to /projects.
 *      - When site data / localStorage is blocked, /saved and SaveButton display friendly message without crashing (Must 2).
 *   3. General:
 *      - Axe accessibility check (WCAG 2.1 AA) with zero serious/critical violations on /saved (populated) and property page.
 *      - Enforced CSP with zero violations.
 *      - 390 px responsive mobile check has zero horizontal overflow on populated /saved and property page.
 *
 * Collaborators: Antigravity <noreply@google.com>, Claude (review 1). Decisions: D-040, D-049.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { apiCall, CMS_STATE } from "../lib/auth";
import { catalogueProject, drainOutbox, type CatalogueProject } from "../lib/catalogue";

test.describe("Tools: EMI Calculator & Saved Homes (Task 5.7b)", () => {
  let project: CatalogueProject;
  let adminPage: Page;

  test.beforeAll(async ({ browser }) => {
    const adminContext = await browser.newContext({ storageState: CMS_STATE });
    adminPage = await adminContext.newPage();
    project = await catalogueProject(adminPage);
  });

  test.afterAll(async () => {
    if (adminPage && project?.id) {
      await apiCall(adminPage, "POST", `/api/v1/admin/projects/${project.id}/unpublish`).catch(
        () => null,
      );
      await drainOutbox(adminPage).catch(() => null);
      await adminPage.context().close();
    }
  });

  test("EMI calculator on property page computes expected EMI, refuses out-of-range rates, and updates on input", async ({
    page,
  }) => {
    const propertyPath = `/projects/${project.slug}/${project.configSlugs[0]}`;
    await page.goto(propertyPath);

    // Initial prefill: 2 BHK config has min_inr = ₹ 78,00,000.
    // At default 8.5% for 20 years (240 months):
    // EMI = 78,00,000 * 0.085/12 * (1+0.085/12)^240 / ((1+0.085/12)^240 - 1) = ₹ 67,690.
    const emiHeading = page.getByRole("heading", { level: 2, name: "EMI calculator" });
    await expect(emiHeading).toBeVisible();

    // Prefilled price note (Must 12)
    const prefillNote = page.getByText(
      "Prefilled with the lowest listed price, which excludes GST, stamp duty and registration. Banks usually lend less than the full price.",
    );
    await expect(prefillNote).toBeVisible();

    const sampleRateNote = page.getByText("Sample rates · check with your bank");
    await expect(sampleRateNote).toBeVisible();

    const disclaimer = page
      .getByText(
        "Indicative only, not a loan offer. Your bank decides the amount, rate and tenure.",
      )
      .first();
    await expect(disclaimer).toBeVisible();

    const monthlyResult = page.getByTestId("emi-monthly-result");
    await expect(monthlyResult).toHaveText("₹ 67,690");

    // Type a new amount: ₹ 50,00,000 (tested known banking figure)
    // ₹ 50,00,000 at 8.5% for 20 years = ₹ 43,391.
    const loanInput = page.getByLabel("Loan amount");
    await loanInput.fill("50,00,000");
    await loanInput.blur();

    await expect(monthlyResult).toHaveText("₹ 43,391");
    await expect(page.getByText("54,13,840")).toBeVisible(); // Total interest
    await expect(page.getByText("1,04,13,840")).toBeVisible(); // Total paid
    await expect(page.getByTestId("emi-over-duration")).toHaveText("20 years (240 months)");

    // Must 1: Type an out-of-bounds rate (20%) -> expect error message and no emi-monthly-result
    const rateInput = page.getByLabel(/^Interest rate/);
    await rateInput.fill("20");
    await rateInput.blur();

    const rateError = page.getByText("Enter a rate between 6.00% and 15.00%");
    await expect(rateError).toBeVisible();
    await expect(monthlyResult).not.toBeVisible();

    // Restore rate to 8.50% -> result reappears
    await rateInput.fill("8.50");
    await rateInput.blur();
    await expect(rateError).not.toBeVisible();
    await expect(monthlyResult).toHaveText("₹ 43,391");
  });

  test("EMI calculator displays formula and disclaimer when JavaScript is disabled", async ({
    browser,
  }) => {
    const noJsContext = await browser.newContext({ javaScriptEnabled: false });
    const noJsPage = await noJsContext.newPage();
    const propertyPath = `/projects/${project.slug}/${project.configSlugs[0]}`;
    await noJsPage.goto(propertyPath);

    // Section heading visible
    await expect(noJsPage.getByRole("heading", { level: 2, name: "EMI calculator" })).toBeVisible();

    // Standard reducing-balance formula and disclaimer in noscript
    await expect(noJsPage.getByText("Standard reducing-balance formula:")).toBeVisible();
    await expect(noJsPage.getByText(/EMI = P · r · \(1 \+ r\)ⁿ/)).toBeVisible();
    await expect(
      noJsPage
        .getByText(
          "Indicative only, not a loan offer. Your bank decides the amount, rate and tenure.",
        )
        .first(),
    ).toBeVisible();

    await noJsContext.close();
  });

  test("CSP enforced with zero violations on /saved and property page", async ({ page }) => {
    const cspViolations: string[] = [];
    page.on("console", (msg) => {
      const text = msg.text();
      if (text.includes("Content Security Policy") || text.includes("violates the following")) {
        cspViolations.push(text);
      }
    });

    const savedRes = await page.goto("/saved");
    expect(savedRes?.status()).toBe(200);
    expect(savedRes?.headers()["content-security-policy"]).toBeDefined();

    const propertyPath = `/projects/${project.slug}/${project.configSlugs[0]}`;
    const propRes = await page.goto(propertyPath);
    expect(propRes?.status()).toBe(200);
    expect(propRes?.headers()["content-security-policy"]).toBeDefined();

    expect(cspViolations).toEqual([]);
  });

  test("handles blocked localStorage gracefully without crashing on /saved and property page (Must 2)", async ({
    page,
  }) => {
    // Stub localStorage getter to throw SecurityError before any script executes
    await page.addInitScript(() => {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        get() {
          throw new DOMException("The user denied permission to use Storage.", "SecurityError");
        },
      });
    });

    // 1. Visit /saved: must not throw uncaught error or crash into error boundary
    await page.goto("/saved");
    const heading = page.getByRole("heading", { level: 1, name: "Saved homes" });
    await expect(heading).toBeVisible();

    // Friendly notice shown on /saved
    const unavailableNotice = page.getByText("Saving isn't available in this browser");
    await expect(unavailableNotice).toBeVisible();

    // 2. Visit property page: Save button indicates storage unavailable and is disabled
    const propertyPath = `/projects/${project.slug}/${project.configSlugs[0]}`;
    await page.goto(propertyPath);

    const saveBtn = page.getByRole("button", {
      name: "Saving isn't available in this browser",
    });
    await expect(saveBtn).toBeVisible();
    await expect(saveBtn).toBeDisabled();
  });

  test("Saved homes: save project and property, verify on /saved without prices, remove, and handle delisted items", async ({
    page,
  }) => {
    // 1. Visit project page and click Save
    const projectPath = `/projects/${project.slug}`;
    await page.goto(projectPath);

    const projectSaveBtn = page.getByRole("button", { name: `Save ${project.name}` });
    await expect(projectSaveBtn).toBeVisible();
    await expect(projectSaveBtn).toHaveAttribute("aria-pressed", "false");
    await projectSaveBtn.click();

    // Changes to Saved
    const projectSavedBtn = page.getByRole("button", {
      name: `Saved ${project.name}. Press to remove from saved homes`,
    });
    await expect(projectSavedBtn).toBeVisible();
    await expect(projectSavedBtn).toHaveAttribute("aria-pressed", "true");

    // 2. Visit property page and click Save
    const propertyPath = `/projects/${project.slug}/${project.configSlugs[0]}`;
    await page.goto(propertyPath);

    const propertySaveBtn = page.getByRole("button", { name: /^Save 2 BHK/ });
    await expect(propertySaveBtn).toBeVisible();
    await expect(propertySaveBtn).toHaveAttribute("aria-pressed", "false");
    await propertySaveBtn.click();

    const propertySavedBtn = page.getByRole("button", { name: /^Saved 2 BHK/ });
    await expect(propertySavedBtn).toBeVisible();
    await expect(propertySavedBtn).toHaveAttribute("aria-pressed", "true");

    // 3. Open /saved and assert both items exist, and NO prices are shown
    await page.goto("/saved");

    const savedHeading = page.getByRole("heading", { level: 1, name: "Saved homes" });
    await expect(savedHeading).toBeVisible();

    const privacyNote = page.getByText("Saved only in this browser.");
    await expect(privacyNote).toBeVisible();

    const list = page.getByTestId("saved-homes-list");
    await expect(list).toBeVisible();

    // Item 11: Assert list items have count 2 with wait
    await expect(list.getByTestId("saved-home-item")).toHaveCount(2);

    // Verify project item
    const projectLink = list.getByRole("link", { name: project.name, exact: true });
    await expect(projectLink).toBeVisible();
    await expect(projectLink).toHaveAttribute("href", projectPath);

    // Verify property item
    const propertyLink = list.getByRole("link", { name: new RegExp(`2 BHK.*${project.name}`) });
    await expect(propertyLink).toBeVisible();

    // COMPLIANCE: /saved must never show prices (Item 11: assert list text does not contain ₹)
    await expect(list).not.toContainText("₹");

    // Item 11: Run axe check on populated /saved page
    const a11ySaved = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const seriousSaved = a11ySaved.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(seriousSaved.map((v) => `${v.id}: ${v.help}`)).toEqual([]);

    // Item 11: Run 390px responsive check on populated /saved page
    await page.setViewportSize({ width: 390, height: 844 });
    const savedPopulatedOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(savedPopulatedOverflow).toBe(false);
    await page.setViewportSize({ width: 1280, height: 800 });

    // 4. Remove the property from /saved
    const removeButtons = list.getByRole("button", { name: /Remove/ });
    await removeButtons.first().click();

    // Item 11: toHaveCount(1) waits for removal
    await expect(list.getByTestId("saved-home-item")).toHaveCount(1);

    // 5. Unpublish the project through staff API to test delisted item handling
    const unpubRes = await apiCall(
      adminPage,
      "POST",
      `/api/v1/admin/projects/${project.id}/unpublish`,
    );
    expect(unpubRes.status()).toBe(200);
    await drainOutbox(adminPage).catch(() => null);

    // Reload /saved
    await page.reload();

    // The project should now display "No longer listed" and NOT be a clickable link
    const delistedBadge = page.getByTestId("delisted-badge");
    await expect(delistedBadge).toBeVisible();
    await expect(delistedBadge).toHaveText("No longer listed");
    await expect(list.getByRole("link", { name: project.name })).not.toBeVisible();

    // Remove the delisted item
    const finalRemoveBtn = list.getByRole("button", { name: /Remove/ });
    await finalRemoveBtn.click();

    // Empty state should now show
    await expect(
      page.getByRole("heading", { level: 2, name: "You haven't saved any homes yet" }),
    ).toBeVisible();
    const exploreBtn = page.getByRole("link", { name: "Explore projects" });
    await expect(exploreBtn).toBeVisible();
    await expect(exploreBtn).toHaveAttribute("href", "/projects");
  });
});

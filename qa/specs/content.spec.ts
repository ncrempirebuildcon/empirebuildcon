// Content journeys (Phase 4 part 4): a page built from blocks (hero, text, numbers, call to
// action, FAQs) with the honesty and link checks, reordered from the keyboard, published, then
// renamed (the redirect appears); a post with a cover; a project FAQ; offers and their states;
// a testimonial that can't be shown without its source and consent; a refused redirect loop; and
// a legal page marked DRAFT that only `legal.publish` can publish.
//
// No new sign-ins and no public submissions: the saved super-admin and sales sessions are reused
// and test data is made through the staff API (qa/README.md).
import { expect, test, type Locator, type Page } from "@playwright/test";
import { CMS_STATE, SALES_STATE, apiCall, runId } from "../lib/auth";
import { draftPage, libraryPhoto, seededLegalPage } from "../lib/content";
import { samplePhoto } from "../lib/files";
import { istDate } from "../lib/leads";

test.use({ storageState: CMS_STATE });

/** The block list on the page editor's Blocks tab. */
const blockList = (page: Page) => page.getByRole("list", { name: "Blocks in page order" });
/** The settings card of the selected block. */
const settings = (page: Page) => page.getByRole("region", { name: /· block \d+$/ });

async function addBlock(page: Page, name: string) {
  await page.getByRole("button", { name: "+ Add block" }).click();
  const palette = page.getByRole("dialog", { name: "Add a block" });
  await palette.getByRole("button", { name: new RegExp(`^${name} `) }).click();
  await expect(palette).toBeHidden();
  // Focus lands on the new block's settings heading, so keyboard users continue there.
  await expect(
    page.getByRole("heading", { level: 2, name: new RegExp(`^${name} · block`) }),
  ).toBeFocused();
}

function status(page: Page, text: string | RegExp): Locator {
  return page.getByRole("status").filter({ hasText: text });
}

test.describe("a page built from blocks", () => {
  test.describe.configure({ mode: "serial" });
  const id = runId();
  const title = `E2E Page ${id}`;
  let pageUrl = "";
  let slug = "";

  test("an editor creates a page", async ({ page }) => {
    await page.goto("/admin");
    await page
      .getByRole("navigation", { name: "Sections" })
      .getByRole("link", { name: "Pages" })
      .click();
    await expect(page.getByRole("heading", { level: 1, name: "Pages" })).toBeVisible();
    await page.getByRole("link", { name: "+ New page" }).click();
    await page.getByRole("textbox", { name: /^Title/ }).fill(title);
    slug = await page.getByRole("textbox", { name: /^Web address/ }).inputValue();
    expect(slug).toBe(`e2e-page-${id}`);
    await page.getByRole("button", { name: "Create draft" }).click();
    await expect(page).toHaveURL(/\/admin\/pages\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    pageUrl = page.url();
  });

  test("blocks are added, checked, reordered and published", async ({ page }) => {
    await page.goto(pageUrl);
    await expect(page.getByText("No blocks yet.")).toBeVisible();

    await addBlock(page, "Hero");
    await settings(page)
      .getByRole("textbox", { name: /^Heading/ })
      .fill(`E2E hero ${id}`);

    await addBlock(page, "Text");
    await settings(page)
      .getByRole("textbox", { name: /^Text/ })
      .fill("*E2E bold* intro\n- one\n  - nested");
    // The live preview uses the same safe renderer as the website.
    const preview = page.getByRole("group", { name: "Preview of Text" });
    await expect(preview.locator("strong")).toHaveText("E2E bold");
    await expect(preview.locator("ul ul li")).toHaveText("nested");

    // Numbers must say where they come from: Save is stopped and the field says why.
    await addBlock(page, "Numbers");
    const stat = settings(page);
    await stat.getByRole("textbox", { name: /^Number/ }).fill("[n]");
    await stat.getByRole("textbox", { name: /^What it counts/ }).fill("E2E test count");
    await stat.getByLabel(/^True as of/).fill(istDate(-1));
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(
      page.getByRole("alert").filter({ hasText: "Some fields need attention." }),
    ).toBeVisible();
    await expect(stat.getByText("Say where this number comes from.")).toBeVisible();
    await expect(blockList(page).getByText("Needs attention")).toBeVisible();
    await stat
      .getByRole("textbox", { name: /^Where this number comes from/ })
      .fill("E2E test register");

    // A button that would run code is refused next to its field.
    await addBlock(page, "Call to action");
    const cta = settings(page);
    await cta.getByRole("textbox", { name: "Button text" }).fill("E2E contact");
    await cta.getByRole("textbox", { name: "Link" }).fill("javascript:alert(1)");
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(
      cta.getByText("Links that run code (javascript:, data: and similar) aren't allowed."),
    ).toBeVisible();
    await cta.getByRole("textbox", { name: "Link" }).fill("/contact");

    await addBlock(page, "FAQs");
    await expect(blockList(page).getByRole("listitem")).toHaveCount(5);

    // Reorder from the keyboard: the move is announced and focus stays on the button.
    const up = page.getByRole("button", { name: "Move FAQs block 5 up" });
    await up.focus();
    await page.keyboard.press("Enter");
    await expect(status(page, "FAQs moved to position 4 of 5.")).toBeAttached();
    await expect(page.getByRole("button", { name: "Move FAQs block 4 up" })).toBeFocused();
    await expect(blockList(page).getByRole("listitem").nth(3)).toContainText("4. FAQs");

    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(status(page, /^Saved\.$/)).toBeVisible();
    await expect(page.getByText("All changes saved")).toBeVisible();

    await page.getByRole("button", { name: "Publish", exact: true }).click();
    await expect(status(page, "Published. The page is live.")).toBeVisible();

    // After a reload the saved order and content come from the API.
    await page.reload();
    await expect(blockList(page).getByRole("listitem")).toHaveCount(5);
    await expect(blockList(page).getByRole("listitem").nth(3)).toContainText("4. FAQs");
    await expect(blockList(page).getByRole("listitem").nth(4)).toContainText("5. Call to action");
  });

  test("the API refuses a number without a source and a javascript: link", async ({ page }) => {
    const pageId = pageUrl.split("/").pop() ?? "";
    const stats = await apiCall(page, "PUT", `/api/v1/admin/pages/${pageId}/blocks`, {
      blocks: [
        {
          type: "stats",
          data: {
            heading: null,
            note: null,
            items: [{ value: "[n]", label: "E2E", as_of: istDate(-1) }],
          },
        },
      ],
    });
    expect(stats.status()).toBe(422);
    const link = await apiCall(page, "PUT", `/api/v1/admin/pages/${pageId}/blocks`, {
      blocks: [
        {
          type: "cta",
          data: { heading: null, text: null, label: "E2E", href: "javascript:alert(1)" },
        },
      ],
    });
    expect(link.status()).toBe(422);
  });

  test("renaming the live page makes its old address redirect", async ({ page }) => {
    await page.goto(`${pageUrl}?tab=settings`);
    const address = page.getByRole("textbox", { name: /^Web address/ });
    await address.fill(`${slug}-moved`);
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(
      status(page, `The old address /${slug} now redirects to /${slug}-moved.`),
    ).toBeVisible();

    await page.goto(`/admin/redirects?q=${slug}`);
    const row = page.getByRole("row", { name: new RegExp(`/${slug}\\b`) });
    await expect(row).toContainText(`/${slug}-moved`);
    await expect(row).toContainText("Page renamed");
  });
});

test("an editor writes a post with a cover image", async ({ page }) => {
  const id = runId();
  await page.goto("/admin/posts");
  await expect(page.getByRole("navigation", { name: "Offers & blog sections" })).toBeVisible();
  await page.getByRole("link", { name: "+ New post" }).click();
  await page.getByRole("textbox", { name: /^Title/ }).fill(`E2E Post ${id}`);
  await page.getByRole("textbox", { name: /^Post/ }).fill("E2E body with *bold* words.");
  await expect(page.getByRole("group", { name: "Preview of Post" }).locator("strong")).toHaveText(
    "bold",
  );

  const cover = page.getByRole("group", { name: "Cover image" });
  const chooser = page.waitForEvent("filechooser");
  await cover.getByRole("button", { name: "Upload a photo for Cover image" }).click();
  await (await chooser).setFiles([samplePhoto(`E2E-cover-${id}.png`, 60)]);
  // The website shows the cover with its honest label, so the upload asks first (review L11);
  // nothing is chosen for the user.
  const question = page.getByRole("dialog", { name: "What is this photo?" });
  await question.getByRole("button", { name: "Upload 1 photo" }).click();
  await expect(question.getByText("Choose what this photo is.")).toBeVisible();
  await question.getByRole("radio", { name: /^Artist's impression/ }).check();
  await question.getByRole("button", { name: "Upload 1 photo" }).click();
  await expect(question).toBeHidden();
  await expect(cover.getByRole("img")).toBeVisible();
  await expect(cover.getByText("Artist's impression", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page).toHaveURL(/\/admin\/posts\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name: `E2E Post ${id}` })).toBeVisible();
  await expect(page.getByRole("group", { name: "Cover image" }).getByRole("img")).toBeVisible();
  await expect(page.getByRole("textbox", { name: /^Web address/ })).toHaveValue(`e2e-post-${id}`);
});

test("an editor adds a FAQ in the project editor", async ({ page }) => {
  const id = runId();
  const created = await apiCall(page, "POST", "/api/v1/admin/projects", {
    name: `E2E FAQ Project ${id}`,
    status: "upcoming",
  });
  expect(created.status()).toBe(201);
  const project = (await created.json()) as { id: string };
  await page.goto(`/admin/projects/${project.id}?tab=faqs`);
  const panel = page.getByRole("tabpanel", { name: "FAQs" });
  await panel.getByRole("button", { name: "+ Add FAQ" }).click();
  const form = page.getByRole("form", { name: "Add FAQ" });
  await form.getByRole("textbox", { name: /^Question/ }).fill(`E2E question ${id}?`);
  await form.getByRole("textbox", { name: /^Answer/ }).fill("E2E answer with *bold*.");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(panel.getByText(`E2E question ${id}?`)).toBeVisible();
  await expect(status(page, "The FAQ was added.")).toBeAttached();

  // The project's FAQs are on the project (part 1's TODO) and on /admin/faqs.
  const read = await apiCall(page, "GET", `/api/v1/admin/projects/${project.id}`);
  const { faqs } = (await read.json()) as { faqs: Array<{ question: string }> };
  expect(faqs.map((faq) => faq.question)).toContain(`E2E question ${id}?`);
  await page.goto(`/admin/faqs?project=${project.id}`);
  await expect(page.getByText(`E2E question ${id}?`)).toBeVisible();
});

test("offers show their state from their dates", async ({ page }) => {
  const id = runId();
  await page.goto("/admin/offers");
  await page.getByRole("button", { name: "+ New offer" }).click();
  const editor = page.getByRole("region", { name: "New offer" });
  await expect(editor.getByRole("note").filter({ hasText: "No countdown timers" })).toBeVisible();
  await editor.getByRole("textbox", { name: /^Offer name/ }).fill(`E2E Offer live ${id}`);
  await editor.getByRole("group", { name: "Starts" }).getByLabel("Date").fill(istDate(-1));
  await editor.getByRole("group", { name: "Ends" }).getByLabel("Date").fill(istDate(10));
  await editor.getByRole("checkbox", { name: /Switched on/ }).check();
  await editor.getByRole("button", { name: "Add offer" }).click();
  await expect(status(page, `Added “E2E Offer live ${id}”: live.`)).toBeVisible();
  // The list is paged (25 a page, review L10) and earlier runs leave offers behind, so the row is
  // looked for under its state filter, where the newest sort near the top.
  const list = page.getByRole("region", { name: "All offers" });
  await expect(page.getByRole("navigation", { name: "Pages of offers" })).toBeVisible();
  await list.getByRole("combobox", { name: "Status" }).selectOption({ label: "Live" });
  await expect(page).toHaveURL(/state=live/);
  await expect(page.getByRole("row", { name: new RegExp(`E2E Offer live ${id}`) })).toContainText(
    "Live",
  );

  // A price without terms is stopped before saving (and by the API).
  await page.getByRole("button", { name: "+ New offer" }).click();
  const next = page.getByRole("region", { name: "New offer" });
  await next.getByRole("textbox", { name: /^Offer name/ }).fill(`E2E Offer later ${id}`);
  await next
    .getByRole("textbox", { name: /^Details shown to buyers/ })
    .fill("E2E 5% off the base price");
  await next.getByRole("group", { name: "Starts" }).getByLabel("Date").fill(istDate(5));
  await next.getByRole("checkbox", { name: /Switched on/ }).check();
  await next.getByRole("button", { name: "Add offer" }).click();
  await expect(next.getByText(/^This offer mentions a price or a discount/)).toBeVisible();
  await next
    .getByRole("textbox", { name: /^Terms line/ })
    .fill("E2E terms: [what it includes], [until when]");
  await next.getByRole("button", { name: "Add offer" }).click();
  await expect(status(page, `Added “E2E Offer later ${id}”: scheduled.`)).toBeVisible();
  await list.getByRole("combobox", { name: "Status" }).selectOption({ label: "Scheduled" });
  await expect(page.getByRole("row", { name: new RegExp(`E2E Offer later ${id}`) })).toContainText(
    "Scheduled",
  );
});

test("a testimonial can't be shown without its source and consent date", async ({ page }) => {
  const id = runId();
  await page.goto("/admin/testimonials");
  await expect(page.getByRole("note").filter({ hasText: "Real testimonials only" })).toBeVisible();
  await page.getByRole("button", { name: "+ Add testimonial" }).click();
  const editor = page.getByRole("region", { name: "Add a testimonial" });
  await editor.getByRole("textbox", { name: /^Buyer's name/ }).fill(`E2E Buyer ${id}`);
  await editor.getByRole("textbox", { name: /^Their words/ }).fill("E2E words for the test only.");
  // No source and no consent date yet: showing is locked.
  const show = editor.getByRole("checkbox", { name: "Show on the website" });
  await expect(show).toBeDisabled();
  await editor.getByRole("combobox", { name: /^Where it came from/ }).fill("E2E test form");
  await expect(show).toBeDisabled();
  await editor.getByRole("button", { name: "Add testimonial" }).click();
  await expect(
    status(page, `${`E2E Buyer ${id}`}'s testimonial is not shown on the website yet.`),
  ).toBeVisible();

  // In the list the switch stays locked and says why, in words.
  const card = page.getByRole("listitem").filter({ hasText: `E2E Buyer ${id}` });
  await expect(card.getByText("Locked: record the consent date before showing it.")).toBeVisible();
  await expect(card.getByRole("switch", { name: /Show on website/ })).toHaveAttribute(
    "aria-disabled",
    "true",
  );

  // The API refuses it too.
  const list = await apiCall(page, "GET", "/api/v1/admin/testimonials?per_page=100");
  const { items } = (await list.json()) as { items: Array<{ id: string; person_name: string }> };
  const saved = items.find((item) => item.person_name === `E2E Buyer ${id}`);
  expect(saved).toBeTruthy();
  const show422 = await apiCall(page, "PATCH", `/api/v1/admin/testimonials/${saved?.id}`, {
    is_visible: true,
  });
  expect(show422.status()).toBe(422);
});

test("a redirect loop is refused with the API's explanation", async ({ page }) => {
  const id = runId();
  const first = await apiCall(page, "POST", "/api/v1/admin/redirects", {
    from_path: `/e2e-a-${id}`,
    to_path: `/e2e-b-${id}`,
  });
  expect(first.status(), await first.text()).toBe(201);

  await page.goto("/admin/redirects");
  await page.getByRole("button", { name: "+ New redirect" }).click();
  const editor = page.getByRole("region", { name: "New redirect" });
  await editor.getByRole("textbox", { name: /^Old address/ }).fill(`/e2e-b-${id}`);
  await editor.getByRole("textbox", { name: /^Send visitors to/ }).fill(`/e2e-a-${id}`);
  await editor.getByRole("button", { name: "Add redirect" }).click();
  await expect(editor.getByRole("alert")).toContainText("loop");

  // A chain is collapsed instead, and the notice says so.
  await editor.getByRole("textbox", { name: /^Old address/ }).fill(`/e2e-c-${id}`);
  await editor.getByRole("button", { name: "Add redirect" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: `/e2e-c-${id} → /e2e-b-${id}` }),
  ).toBeVisible();
});

test("a legal page shows DRAFT, and publishing it needs legal.publish", async ({
  page,
  browser,
}) => {
  const legal = await seededLegalPage(page);
  await page.goto(`/admin/pages/${legal.id}`);
  const banner = page.getByRole("note", { name: "Legal page" });
  await expect(banner).toContainText("DRAFT");
  await expect(banner).toContainText("needs the legal.publish permission");

  // A role without legal.publish is refused by the API (the sales session; no new sign-in).
  const sales = await browser.newContext({ storageState: SALES_STATE });
  const salesPage = await sales.newPage();
  const refused = await apiCall(salesPage, "POST", `/api/v1/admin/pages/${legal.id}/publish`);
  expect(refused.status()).toBe(403);
  await sales.close();
});

test("a library photo can be chosen for a hero block", async ({ page }) => {
  const photoTitle = `E2E hero photo ${runId()}`;
  await libraryPhoto(page, photoTitle);
  const draft = await draftPage(page);
  await page.goto(`/admin/pages/${draft.id}`);
  await addBlock(page, "Hero");
  const hero = settings(page);
  await hero.getByRole("button", { name: "Choose from the library: Image" }).click();
  const picker = page.getByRole("dialog", { name: "Choose a photo from the library" });
  await picker.getByRole("searchbox", { name: "Search" }).fill(photoTitle);
  await picker.getByRole("radio", { name: photoTitle }).check({ force: true });
  await picker.getByRole("button", { name: "Use this photo" }).click();
  await expect(
    hero.getByRole("group", { name: "Image" }).getByText(photoTitle, { exact: true }),
  ).toBeVisible();
});

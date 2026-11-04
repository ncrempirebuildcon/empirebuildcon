/**
 * Helpers for the content journeys (Phase 4 part 4): pages, posts, a library photo and the
 * seeded legal pages, all set up through the staff API as the signed-in user (no sign-ins, no
 * public submissions; qa/README.md "Sign-in limit").
 *
 * Everything made here is named "E2E …" with a run id, so runs never clash on slugs in the shared
 * `empire_dev` database and nothing can pass for real content.
 */
import { expect, type Page } from "@playwright/test";
import { apiCall, apiUpload, runId } from "./auth";
import { samplePhoto } from "./files";

export interface PageRef {
  id: string;
  slug: string;
  path: string;
  title: string;
}

/** A draft page made through the API. */
export async function draftPage(
  page: Page,
  kind: "standard" | "landing" | "legal" = "standard",
): Promise<PageRef> {
  const id = runId();
  const response = await apiCall(page, "POST", "/api/v1/admin/pages", {
    title: `E2E ${kind} page ${id}`,
    slug: `e2e-${kind}-${id}`,
    kind,
  });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as PageRef;
}

/** A photo uploaded to the library only (attached to nothing), with an honest label. */
export async function libraryPhoto(page: Page, title = `E2E photo ${runId()}`): Promise<string> {
  const response = await apiUpload(page, "/api/v1/admin/media/images", {
    file: samplePhoto(`${title.replace(/\W+/g, "-")}.png`, 40),
    title,
    label: "artist_impression",
  });
  expect(response.status(), await response.text()).toBe(201);
  return ((await response.json()) as { id: string }).id;
}

/** A seeded legal page (privacy, terms or disclaimer), marked DRAFT until the owner approves. */
export async function seededLegalPage(page: Page): Promise<PageRef & { is_draft_text: boolean }> {
  // WHY by slug: runs leave many "E2E" legal pages behind, which can push the seeded ones off
  // the first page of a plain list (task 5.8).
  let seeded: (PageRef & { is_draft_text: boolean }) | undefined;
  for (const slug of ["privacy", "terms", "disclaimer"]) {
    const response = await apiCall(
      page,
      "GET",
      `/api/v1/admin/pages?kind=legal&q=${slug}&per_page=50`,
    );
    expect(response.status()).toBe(200);
    const { items } = (await response.json()) as {
      items: Array<PageRef & { is_draft_text: boolean }>;
    };
    seeded = items.find((item) => item.slug === slug && item.is_draft_text);
    if (seeded) break;
  }
  expect(seeded, "a seeded legal page marked DRAFT (empire-api seed)").toBeTruthy();
  return seeded as PageRef & { is_draft_text: boolean };
}

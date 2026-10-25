"use client";
/**
 * Publishing actions for a page (components/admin/content/usePublishActions.tsx does the work).
 *
 * Rules (ARCHITECTURE §6 and §11, spec Phase 4 part 4 §3):
 *   - Publish and Unpublish need `content.publish`; a legal page needs `legal.publish` instead
 *     (D-017). Production refuses to publish a legal page whose text still says DRAFT; the API
 *     answers 409 and its message is shown as it comes.
 *   - Only drafts that were never published can be deleted; pages that come with the website
 *     (`is_required`) never, and they can't be archived either. Unpublishing them is allowed.
 *   - Archiving a live page takes it off the website, a publishing decision, so it needs the
 *     publish permission too (PagePublishPanel.tsx).
 * SECURITY: the buttons only show with the permission; the API checks every call again.
 */
import { api, call } from "@/lib/api";
import { PAGES_PATH } from "@/lib/routes";
import {
  usePublishActions,
  type PublishActions,
} from "@/components/admin/content/usePublishActions";
import type { Page } from "./pageForm";

/**
 * True when the API would allow Delete: a draft, never published, and not a page that comes
 * with the website (`is_required`: system pages and the seeded legal pages; review L8).
 */
export function canBeDeleted(page: Page): boolean {
  return !page.is_required && page.publish_state === "draft" && !page.published_at;
}

export function usePageActions(options: {
  page: Page;
  onUpdated: (page: Page) => void;
  refresh: () => Promise<unknown>;
  onNotice: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { page } = options;
  const path = { params: { path: { id: page.id } } };
  return usePublishActions<Page>({
    ...options,
    noun: "page",
    title: page.title,
    afterDelete: `${PAGES_PATH}?notice=deleted`,
    calls: {
      publish: () => call(api.POST("/api/v1/admin/pages/{id}/publish", path)),
      unpublish: () => call(api.POST("/api/v1/admin/pages/{id}/unpublish", path)),
      setState: (state) =>
        call(api.PATCH("/api/v1/admin/pages/{id}", { ...path, body: { publish_state: state } })),
      remove: () => call(api.DELETE("/api/v1/admin/pages/{id}", path)),
    },
  });
}

export type PageActions = PublishActions;

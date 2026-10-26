"use client";
/**
 * The page editor (board NoirCmsPage): a status bar with Save draft and Publish, the Blocks,
 * Settings and SEO tabs, and the publishing panel.
 *
 * How saving works (one "Save draft" button, like the project editor):
 *   1. The page's own fields (Settings, SEO) are one form, saved with PATCH (changed fields only,
 *      pageForm.ts). The blocks are one ordered list, saved with PUT `/pages/{id}/blocks` in one
 *      transaction. Save sends whichever changed, fields first.
 *   2. Before sending, the form and every block are checked (pageForm.ts `checkForm`,
 *      blocks/blockDraft.ts `checkBlock`). Problems show next to their fields, blocks with
 *      problems say "Needs attention", and a summary links to them.
 *   3. API errors come back the same way: "slug" or "seo.title" on the form, and
 *      "blocks.3.data.items.0.source" on block 4's field.
 *   4. After a save the editor takes the API's version, so new blocks get their ids; the
 *      selected block stays selected (matched by position).
 *   5. Leaving with unsaved changes asks first (useUnsavedChanges); Publish waits for a save.
 *   6. Two people saving the same page (review L7): each save sends the `updated_at` of the
 *      version this editor holds as `expected_updated_at`. If someone saved in between, the API
 *      answers 409 and the editor offers to reload (a fresh editor from the saved page), instead
 *      of silently replacing their blocks with this tab's older list.
 *
 * Permissions: `content.write` edits; `seo.manage` edits the SEO tab; publishing needs
 * `content.publish`, or `legal.publish` for legal pages, which also guards any change to a legal
 * page that is live or scheduled (lib/content/pages.ts). The API checks
 * all of them again (SECURITY: hiding is not the protection).
 */
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, Button, LiveRegion, TabPanel, Tabs } from "@empire/ui";
import { api, call } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { PAGE_KIND } from "@/lib/content/labels";
import { fromInstant } from "@/lib/content/schedule";
import { canEditPage, publishPermissionFor, readOnlyReason } from "@/lib/content/pages";
import type { Media } from "@/lib/media/upload";
import { fieldErrors, problemMessage, toProblem, type FieldErrors } from "@/lib/problems";
import { PAGES_PATH } from "@/lib/routes";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { EditorStatusBar, SampleNote } from "@/components/admin/content/EditorStatusBar";
import { SaveErrorSummary } from "@/components/admin/content/SaveErrorSummary";
import { SeoFields } from "@/components/admin/content/SeoFields";
import { useLoad } from "@/components/admin/useLoad";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { useAdminHeading, useAdminSession } from "../../session-context";
import { BlocksTab } from "./blocks/BlocksTab";
import {
  blockErrors,
  blockName,
  checkBlock,
  toDrafts,
  toInputs,
  type DraftBlock,
} from "./blocks/blockDraft";
import { BlockMediaContext, type BlockMedia } from "./blocks/fields";
import { LegalBanner } from "./LegalBanner";
import { PagePublishPanel } from "./PagePublishPanel";
import { SettingsTab } from "./SettingsTab";
import {
  checkForm,
  hasProblems,
  sameForm,
  toForm,
  toUpdate,
  type Page,
  type PageForm,
} from "./pageForm";
import { usePageActions } from "./usePageActions";

const TABS = [
  { id: "blocks", label: "Blocks" },
  { id: "settings", label: "Settings" },
  { id: "seo", label: "SEO" },
] as const;
type TabId = (typeof TABS)[number]["id"];
const isTab = (value: string | null): value is TabId => TABS.some((t) => t.id === value);

/** Which tab shows a page field's error. */
const tabForField = (field: string): TabId => (field.startsWith("seo.") ? "seo" : "settings");

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  slug: "Web address",
  kind: "Kind",
  nav_order: "Position in the menu",
  legal_version: "Legal text version",
  publish_at: "Publish on",
  unpublish_at: "Take down on",
  "seo.title": "Search title",
  "seo.description": "Search description",
  "seo.canonical_path": "Canonical path",
  "seo.og_image_id": "Share image",
};

export function PageEditor({ id }: { id: string }) {
  const page = useLoad(`page:${id}`, () =>
    call(api.GET("/api/v1/admin/pages/{id}", { params: { path: { id } } })),
  );
  useAdminHeading(page.data?.title ?? null);
  // A new editor (fresh state from the saved page) after "Reload the page" on a stale save.
  const [generation, setGeneration] = useState(0);
  const { refresh } = page;
  const reload = useCallback(async () => {
    await refresh();
    setGeneration((n) => n + 1);
  }, [refresh]);

  if (page.error && !page.data) {
    if (toProblem(page.error).status === 404) {
      return (
        <Alert tone="error" title="This page doesn't exist or was deleted.">
          <Link href={PAGES_PATH} className="font-bold underline">
            Back to pages
          </Link>
        </Alert>
      );
    }
    return (
      <ErrorPanel
        message={problemMessage(page.error, "Couldn't load the page.")}
        onRetry={page.reload}
      />
    );
  }
  if (!page.data) return <LoadingPanel label="Loading the page…" rows={8} />;
  return (
    <EditorBody
      key={generation}
      page={page.data}
      replace={page.replace}
      refresh={page.refresh}
      reload={reload}
    />
  );
}

/** True for the API's "someone else saved this page" answer (409 at `expected_updated_at`). */
function isStaleSave(error: unknown): boolean {
  return toProblem(error).status === 409 && "expected_updated_at" in fieldErrors(error);
}

function EditorBody({
  page,
  replace,
  refresh,
  reload,
}: {
  page: Page;
  replace: (page: Page) => void;
  refresh: () => Promise<Page>;
  /** Reads the page again and starts a fresh editor (unsaved changes here are dropped). */
  reload: () => Promise<void>;
}) {
  const { can } = useAdminSession();
  const params = useSearchParams();
  const canPublish = can(publishPermissionFor(page));
  // SECURITY (mirrors the API): a live or scheduled legal page changes only with legal.publish
  // (D-017; review H2, lib/content/pages.ts).
  const canWrite = canEditPage(page, can);
  const readOnly = readOnlyReason(page, can);
  const canSeo = can("seo.manage");
  const canUpload = can("media.upload");

  const [tab, setTabState] = useState<TabId>(() => {
    const fromUrl = params.get("tab");
    return isTab(fromUrl) ? fromUrl : "blocks";
  });
  const setTab = useCallback((next: string) => {
    if (!isTab(next)) return;
    setTabState(next);
    // WHY: keep the tab in the address so a reload or a shared link opens the same section.
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url);
  }, []);

  // The library items the blocks and the share image use, for thumbnails (Page.media), plus
  // anything chosen or uploaded since.
  const [mediaById, setMediaById] = useState(
    () =>
      new Map<string, Media>(
        [...page.media, ...(page.og_image ? [page.og_image] : [])].map((item) => [item.id, item]),
      ),
  );
  const media = useMemo<BlockMedia>(
    () => ({
      get: (mediaId) => (mediaId ? (mediaById.get(mediaId) ?? null) : null),
      remember: (item) =>
        setMediaById((current) =>
          current.get(item.id) === item ? current : new Map(current).set(item.id, item),
        ),
    }),
    [mediaById],
  );

  const [form, setFormState] = useState<PageForm>(() => toForm(page, media.get));
  const [savedForm, setSavedForm] = useState<PageForm>(() => toForm(page, media.get));
  const [blocks, setBlocks] = useState<DraftBlock[]>(() => toDrafts(page.blocks));
  const [savedBlocks, setSavedBlocks] = useState(() =>
    JSON.stringify(toInputs(toDrafts(page.blocks))),
  );
  const [selectedKey, setSelectedKey] = useState<string | null>(() => page.blocks[0]?.id ?? null);
  const [apiErrors, setApiErrors] = useState<FieldErrors>({});
  const [apiBlockErrors, setApiBlockErrors] = useState<Map<string, FieldErrors>>(new Map());
  const [showChecks, setShowChecks] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // The API's sentence when someone else saved the page since this editor loaded it (L7).
  const [stale, setStale] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const [message, setMessage] = useState("");
  const uploads = useDirtyParts();

  const formDirty = !sameForm(form, savedForm);
  const blocksDirty = JSON.stringify(toInputs(blocks)) !== savedBlocks;
  const dirty = formDirty || blocksDirty || uploads.dirty;
  const { dialog: leaveDialog } = useUnsavedChanges(dirty);

  const problems = checkForm(form);
  const checks = useMemo(
    () => new Map(blocks.map((block) => [block.key, checkBlock(block)])),
    [blocks],
  );
  const blockProblems = useMemo(() => {
    const out = new Map<string, FieldErrors>();
    for (const block of blocks) {
      const merged = {
        ...(apiBlockErrors.get(block.key) ?? {}),
        ...(showChecks ? checks.get(block.key) : {}),
      };
      if (Object.keys(merged).length > 0) out.set(block.key, merged);
    }
    return out;
  }, [blocks, apiBlockErrors, checks, showChecks]);
  const formErrors: FieldErrors = { ...apiErrors, ...(showChecks ? problems.fields : {}) };

  const setForm = useCallback((patch: Partial<PageForm>) => {
    setFormState((current) => ({ ...current, ...patch }));
    setNotice(null);
  }, []);
  const changeBlocks = useCallback((next: DraftBlock[]) => {
    setBlocks(next);
    setNotice(null);
  }, []);

  const actions = usePageActions({
    page,
    onUpdated: (updated) => {
      replace(updated);
      // WHY: publishing changes the schedule (a take-down clears "Publish on", review M2), so
      // the schedule fields take the saved times; other unsaved typing stays.
      const times = {
        publish_at: fromInstant(updated.publish_at),
        unpublish_at: fromInstant(updated.unpublish_at),
      };
      setSavedForm((current) => ({ ...current, ...times }));
      setFormState((current) => ({ ...current, ...times }));
    },
    refresh,
    onNotice: (text) => {
      setSaveError(null);
      setNotice(text);
    },
    onError: (text) => {
      setNotice(null);
      setSaveError(text);
    },
  });

  /** Takes the API's version of the page after a save. */
  function adopt(updated: Page, sentBlocks: DraftBlock[] | null) {
    replace(updated);
    updated.media.forEach(media.remember);
    const nextForm = toForm(
      updated,
      (mediaId) => media.get(mediaId) ?? updated.media.find((m) => m.id === mediaId) ?? null,
    );
    setSavedForm(nextForm);
    setFormState(nextForm);
    if (sentBlocks) {
      const drafts = toDrafts(updated.blocks);
      setBlocks(drafts);
      setSavedBlocks(JSON.stringify(toInputs(drafts)));
      // WHY by position: new blocks had local keys; the saved list comes back in the same order.
      const index = sentBlocks.findIndex((block) => block.key === selectedKey);
      setSelectedKey(index >= 0 ? (drafts[index]?.key ?? null) : (drafts[0]?.key ?? null));
    }
  }

  async function save() {
    if (saving) return;
    setNotice(null);
    setSaveError(null);
    const blocksWithProblems = blocks.filter(
      (block) => Object.keys(checks.get(block.key) ?? {}).length > 0,
    );
    if (hasProblems(problems) || blocksWithProblems.length > 0) {
      setShowChecks(true);
      setSaveError("Some fields need attention.");
      return;
    }
    setShowChecks(false);
    setStale(null);
    setSaving(true);
    const wasLive = page.publish_state === "published";
    const oldPath = page.path;
    try {
      let latest = page;
      if (formDirty) {
        latest = await call(
          api.PATCH("/api/v1/admin/pages/{id}", {
            params: { path: { id: page.id } },
            body: { ...toUpdate(form, savedForm), expected_updated_at: latest.updated_at },
          }),
        );
        // WHY adopt now: if the blocks then fail, the saved fields must not still look unsaved.
        adopt(latest, null);
      }
      const sent = blocksDirty ? blocks : null;
      if (sent) {
        latest = await call(
          api.PUT("/api/v1/admin/pages/{id}/blocks", {
            params: { path: { id: page.id } },
            // The version just saved above, if any: our own PATCH must not look like someone else's.
            body: { blocks: toInputs(sent), expected_updated_at: latest.updated_at },
          }),
        );
      }
      adopt(latest, sent);
      setApiErrors({});
      setApiBlockErrors(new Map());
      setNotice(
        wasLive && latest.path !== oldPath
          ? `Saved. The old address ${oldPath} now redirects to ${latest.path}.`
          : "Saved.",
      );
    } catch (err) {
      if (isStaleSave(err)) {
        setApiErrors({});
        setApiBlockErrors(new Map());
        setStale(
          problemMessage(
            err,
            "Someone else saved this page since you opened it. Reload it to see their changes, then make yours again.",
          ),
        );
        return;
      }
      const found = fieldErrors(err);
      const byIndex = blockErrors(found);
      const byKey = new Map<string, FieldErrors>();
      byIndex.forEach((errs, index) => {
        const block = blocks[index];
        if (block) byKey.set(block.key, errs);
      });
      setApiBlockErrors(byKey);
      setApiErrors(
        Object.fromEntries(Object.entries(found).filter(([field]) => !field.startsWith("blocks"))),
      );
      setSaveError(problemMessage(err, "Couldn't save the page."));
    } finally {
      setSaving(false);
    }
  }

  const state = page.publish_state;
  const blockers = page.publish_blockers;
  const formErrorList = Object.entries(formErrors);
  const scheduleErrors = showChecks ? problems : { publish_at: null, unpublish_at: null };
  const blocksNeedingAttention = blocks
    .map((block, index) => ({ block, index }))
    .filter(({ block }) => blockProblems.has(block.key));

  return (
    <BlockMediaContext.Provider value={media}>
      {page.is_sample ? <SampleNote /> : null}
      {page.kind === "legal" ? <LegalBanner page={page} canPublish={canPublish} /> : null}

      <EditorStatusBar
        isSample={page.is_sample}
        state={state}
        dirty={dirty}
        meta={[
          PAGE_KIND[page.kind],
          page.path,
          `last saved ${formatDateTime(page.updated_at)}${page.updated_by ? ` by ${page.updated_by.name}` : ""}`,
          page.published_at ? `first published ${formatDateTime(page.published_at)}` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        save={
          canWrite ? { onClick: save, busy: saving, disabled: !formDirty && !blocksDirty } : null
        }
        publish={
          canPublish
            ? {
                onClick: actions.publish,
                busy: actions.busy === "publish",
                disabled: blockers.length > 0 || dirty,
                describedBy: "page-publish-status",
              }
            : null
        }
        unpublish={
          canPublish ? { onClick: actions.askUnpublish, busy: actions.busy === "unpublish" } : null
        }
      />

      {notice ? <Alert tone="success">{notice}</Alert> : null}
      {stale ? (
        <Alert tone="error" title="This page was changed by someone else.">
          <p className="mb-3">
            {stale} Reloading replaces the unsaved changes in this tab; copy any text you want to
            keep first.
          </p>
          <Button
            variant="secondary"
            loading={reloading}
            onClick={async () => {
              setReloading(true);
              try {
                await reload();
              } catch (err) {
                setReloading(false);
                setStale(problemMessage(err, "Couldn't reload the page. Try again."));
              }
            }}
          >
            Reload the page
          </Button>
        </Alert>
      ) : null}
      {saveError ? (
        <SaveErrorSummary
          title={saveError}
          problems={[
            ...formErrorList.map(([field, text]) => ({
              key: field,
              text: `${FIELD_LABELS[field] ?? field}: ${text}`,
              onGo: () => setTab(tabForField(field)),
            })),
            ...blocksNeedingAttention.map(({ block, index }) => ({
              key: block.key,
              text: `Block ${index + 1} (${blockName(block)}) needs attention`,
              onGo: () => {
                setTab("blocks");
                setSelectedKey(block.key);
              },
            })),
          ]}
        />
      ) : null}
      {readOnly ? <Alert tone="info">{readOnly}</Alert> : null}

      <div className="flex flex-col gap-4">
        <Tabs label="Page sections" idPrefix="page" tabs={TABS} selected={tab} onSelect={setTab} />
        <TabPanel idPrefix="page" tabId="blocks" selected={tab === "blocks"}>
          <BlocksTab
            blocks={blocks}
            onChange={changeBlocks}
            selectedKey={selectedKey}
            onSelect={setSelectedKey}
            errors={blockProblems}
            canWrite={canWrite}
            canUpload={canUpload}
            onBusyChange={(busy) => uploads.report("blocks", busy)}
            announce={setMessage}
          />
        </TabPanel>
        <TabPanel idPrefix="page" tabId="settings" selected={tab === "settings"}>
          <SettingsTab
            page={page}
            form={form}
            setForm={setForm}
            errors={formErrors}
            schedule={scheduleErrors}
            canWrite={canWrite}
            canPublish={canPublish}
            canChooseLegal={can("legal.publish")}
          />
        </TabPanel>
        <TabPanel idPrefix="page" tabId="seo" selected={tab === "seo"}>
          <SeoFields
            value={form.seo}
            onChange={(patch) => setForm({ seo: { ...form.seo, ...patch } })}
            errors={formErrors}
            warnings={page.seo_warnings}
            path={page.path}
            fallbackTitle={`${form.title.trim() || "[Page title]"} | Empire`}
            fallbackDescription="[Search description]"
            canEdit={canWrite && canSeo}
            canUpload={canUpload}
            noindexHint={
              page.kind === "landing"
                ? "Campaign pages are often hidden from search engines, so only the ad's visitors see them."
                : undefined
            }
            onBusyChange={(busy) => uploads.report("seo", busy)}
          />
        </TabPanel>
      </div>

      <PagePublishPanel
        page={page}
        actions={actions}
        dirty={dirty}
        canWrite={canWrite}
        canPublish={canPublish}
      />
      <LiveRegion message={message} />
      {actions.dialogs}
      {leaveDialog}
    </BlockMediaContext.Provider>
  );
}

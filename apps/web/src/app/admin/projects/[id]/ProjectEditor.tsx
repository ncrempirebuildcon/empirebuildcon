"use client";
/**
 * Project editor (board NoirCmsProject): header with status chips and Save/Publish, the tabbed
 * sections, and the publishing panel.
 *
 * How saving works (the board has one "Save draft" button in the header):
 *   1. The project's own fields (Details, Location address and pin, Documents' RERA account, SEO)
 *      form one draft, saved together with PATCH. Field errors from the API (problem+json
 *      `errors[]`) appear next to their fields, and a summary at the top links to their tabs.
 *   2. Child lists (towers, configurations, …) and amenities save as you go through their own
 *      endpoints; after each change the project is re-read quietly, so the lists and the publish
 *      blockers stay current without touching unsaved fields.
 *   3. Leaving with unsaved fields or an open item form asks first (useUnsavedChanges).
 *
 * Permissions: without projects.write every section is read-only (fieldsets disabled, no
 * buttons); Publish/Unpublish need projects.publish; Delete needs projects.delete. Media
 * (uploads, order, cover, show/hide, floor plans, the RERA QR) needs media.upload instead, which
 * marketing staff have without projects.write (ARCHITECTURE §11). The API checks all of them
 * again (SECURITY: hiding is not the protection).
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, Button, Chip, TabPanel, Tabs } from "@empire/ui";
import { api, call } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import {
  PROJECT_STATUS,
  PROJECT_STATUS_CHIP,
  PUBLISH_STATE,
  PUBLISH_STATE_CHIP,
} from "@/lib/labels";
import { fieldErrors, problemMessage, toProblem, type FieldErrors } from "@/lib/problems";
import { PROJECTS_PATH } from "@/lib/routes";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { useAdminHeading, useAdminSession } from "../../session-context";
import { AmenitiesTab } from "./AmenitiesTab";
import { ConfigurationsTab } from "./ConfigurationsTab";
import { DetailsTab, type OffMarketLock } from "./DetailsTab";
import { DocumentsTab } from "./DocumentsTab";
import { FaqsTab } from "./FaqsTab";
import { LocationTab } from "./LocationTab";
import { MediaTab } from "./MediaTab";
import { PaymentPlansTab } from "./PaymentPlansTab";
import { ProgressTab } from "./ProgressTab";
import { PublishPanel, useProjectActions } from "./PublishPanel";
import { SeoTab } from "./SeoTab";
import { SpecificationsTab } from "./SpecificationsTab";
import { TowersTab } from "./TowersTab";
import {
  FIELD_LABELS,
  mergeAfterSave,
  sameForm,
  tabForField,
  toForm,
  toInput,
  validateForm,
  type ProjectAdmin,
  type ProjectForm,
} from "./projectForm";

const TABS = [
  { id: "details", label: "Details" },
  { id: "towers", label: "Towers" },
  { id: "configurations", label: "Configurations" },
  { id: "amenities", label: "Amenities" },
  { id: "specifications", label: "Specifications" },
  { id: "media", label: "Media" },
  { id: "location", label: "Location" },
  { id: "progress", label: "Progress" },
  { id: "payment-plans", label: "Payment plans" },
  { id: "faqs", label: "FAQs" },
  { id: "documents", label: "Documents" },
  { id: "seo", label: "SEO" },
] as const;
type TabId = (typeof TABS)[number]["id"];
const isTab = (value: string | null): value is TabId => TABS.some((t) => t.id === value);
const tabLabel = (id: string) => TABS.find((t) => t.id === id)?.label ?? "Details";

const NOTICES: Record<string, string> = {
  // COMPLIANCE: Duplicate never copies media, so the copy can't inherit another project's RERA QR.
  duplicated:
    "This is the copy, saved as a draft. Photos, documents and the RERA QR code were not copied: upload this project's own.",
};

export function ProjectEditor({ id }: { id: string }) {
  const project = useLoad(`project:${id}`, () =>
    call(api.GET("/api/v1/admin/projects/{id}", { params: { path: { id } } })),
  );
  useAdminHeading(project.data?.name ?? null);

  if (project.error && !project.data) {
    if (toProblem(project.error).status === 404) {
      return (
        <Alert tone="error" title="This project doesn't exist or was deleted.">
          <Link href={PROJECTS_PATH} className="font-bold underline">
            Back to projects
          </Link>
        </Alert>
      );
    }
    return (
      <ErrorPanel
        message={problemMessage(project.error, "Couldn't load the project.")}
        onRetry={project.reload}
      />
    );
  }
  if (!project.data) return <LoadingPanel label="Loading the project…" rows={8} />;
  return <EditorBody project={project.data} replace={project.replace} refresh={project.refresh} />;
}

function EditorBody({
  project,
  replace,
  refresh,
}: {
  project: ProjectAdmin;
  replace: (project: ProjectAdmin) => void;
  refresh: () => Promise<ProjectAdmin>;
}) {
  const { can } = useAdminSession();
  const params = useSearchParams();
  const canWrite = can("projects.write");
  const canPublish = can("projects.publish");
  const canUpload = can("media.upload");
  const [tab, setTabState] = useState<TabId>(() => {
    const fromUrl = params.get("tab");
    return isTab(fromUrl) ? fromUrl : "details";
  });
  const [form, setFormState] = useState<ProjectForm>(() => toForm(project));
  const [savedForm, setSavedForm] = useState<ProjectForm>(() => toForm(project));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(
    () => NOTICES[params.get("notice") ?? ""] ?? null,
  );
  const [dirtyParts, setDirtyParts] = useState<Record<string, boolean>>({});

  useEffect(() => {
    // A one-off notice (e.g. after Duplicate) is shown once; drop it from the address so a
    // reload doesn't repeat it.
    const url = new URL(window.location.href);
    if (!url.searchParams.has("notice")) return;
    url.searchParams.delete("notice");
    window.history.replaceState(null, "", url);
  }, []);

  const formDirty = !sameForm(form, savedForm);
  const dirty = formDirty || Object.values(dirtyParts).some(Boolean);
  const { dialog: leaveDialog } = useUnsavedChanges(dirty);

  const setForm = useCallback((patch: Partial<ProjectForm>) => {
    setFormState((current) => ({ ...current, ...patch }));
    setNotice(null);
  }, []);
  const reportDirty = useCallback((key: string, value: boolean) => {
    setDirtyParts((current) => (current[key] === value ? current : { ...current, [key]: value }));
  }, []);
  const setTab = useCallback((next: string) => {
    if (!isTab(next)) return;
    setTabState(next);
    setNotice(null);
    // WHY: keep the tab in the address so a reload or a shared link opens the same section.
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    url.searchParams.delete("notice");
    window.history.replaceState(null, "", url);
  }, []);

  const actions = useProjectActions({
    project,
    onUpdated: replace,
    refresh,
    onNotice: (message) => {
      setSaveError(null);
      setNotice(message);
    },
    onError: (message) => {
      setNotice(null);
      setSaveError(message);
    },
  });

  async function save() {
    if (saving) return;
    setNotice(null);
    const found = validateForm(form);
    if (Object.keys(found).length > 0) {
      setErrors(found);
      setSaveError("Some fields need attention.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    const sent = form;
    try {
      const updated = await call(
        api.PATCH("/api/v1/admin/projects/{id}", {
          params: { path: { id: project.id } },
          body: toInput(sent),
        }),
      );
      replace(updated);
      const saved = toForm(updated);
      // WHY merge: fields typed while the request ran keep the new text (and stay "unsaved",
      // so the leave warning still covers them); the others take the saved values.
      setFormState((current) => mergeAfterSave(current, sent, saved));
      setSavedForm(saved);
      setErrors({});
      setNotice("Saved.");
    } catch (err) {
      setErrors(fieldErrors(err));
      setSaveError(problemMessage(err, "Couldn't save the project."));
    } finally {
      setSaving(false);
    }
  }

  // SECURITY (mirrors the API): on a live project, moving into or out of "off market" hides or
  // shows it on the website, which is the projects.publish permission's job, not projects.write's.
  const offMarketLock: OffMarketLock =
    project.publish_state === "published" && !canPublish
      ? project.sales_status === "off_market"
        ? "locked"
        : "no-entry"
      : "none";
  const childProps = { project, canWrite, onChanged: refresh, reportDirty };
  const formProps = { form, setForm, errors, canWrite };
  const state = project.publish_state ?? "draft";
  const blocked = (project.publish_blockers ?? []).length > 0;
  const place = [project.location?.locality?.name, project.location?.city?.name]
    .filter(Boolean)
    .join(", ");
  const errorFields = Object.entries(errors);

  return (
    <>
      {project.is_sample ? (
        <div
          role="note"
          className="flex items-center gap-2.5 rounded-tile border border-danger/60 bg-noir-700 px-4 py-2 text-caption"
        >
          <span aria-hidden="true" className="size-2 shrink-0 rounded-pill bg-danger" />
          Sample data · nothing here is shown on the live site
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3.5">
        <div className="flex flex-wrap items-center gap-2">
          {project.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
          <Chip variant={PUBLISH_STATE_CHIP[state]}>{PUBLISH_STATE[state]}</Chip>
          <Chip variant={PROJECT_STATUS_CHIP[project.status]}>
            {PROJECT_STATUS[project.status]}
          </Chip>
          <span className="text-caption text-muted">
            {[
              place || "No city yet",
              project.rera.number || "No RERA number yet",
              project.updated_at ? `last saved ${formatDateTime(project.updated_at)}` : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {canWrite ? (
            <Button variant="secondary" loading={saving} disabled={!formDirty} onClick={save}>
              {state === "draft" ? "Save draft" : "Save changes"}
            </Button>
          ) : null}
          {canPublish && state === "published" ? (
            <Button
              variant="secondary"
              loading={actions.busy === "unpublish"}
              onClick={actions.askUnpublish}
            >
              Unpublish
            </Button>
          ) : null}
          {canPublish && state === "draft" ? (
            <Button
              loading={actions.busy === "publish"}
              disabled={blocked || dirty}
              aria-describedby="publish-checklist"
              onClick={actions.publish}
            >
              {blocked ? <LockIcon /> : null}
              Publish
            </Button>
          ) : null}
        </div>
      </div>

      {notice ? <Alert tone="success">{notice}</Alert> : null}
      {saveError ? (
        <Alert tone="error" title={saveError}>
          {errorFields.length > 0 ? (
            <ul className="mt-1 flex flex-col gap-1">
              {errorFields.map(([field, message]) => (
                <li key={field}>
                  <button
                    type="button"
                    onClick={() => setTab(tabForField(field))}
                    className="text-left underline underline-offset-4"
                  >
                    {FIELD_LABELS[field] ?? field}: {message}
                  </button>{" "}
                  <span className="text-muted">({tabLabel(tabForField(field))})</span>
                </li>
              ))}
            </ul>
          ) : null}
        </Alert>
      ) : null}
      {!canWrite ? (
        <Alert tone="info">You can view this project. Editing needs an editor or admin role.</Alert>
      ) : null}

      <div className="flex flex-wrap items-start gap-5">
        <section
          aria-label="Project editor"
          className="flex min-w-0 flex-[999_1_680px] flex-col gap-4"
        >
          <Tabs
            label="Project sections"
            idPrefix="project"
            tabs={TABS}
            selected={tab}
            onSelect={setTab}
          />
          <TabPanel idPrefix="project" tabId="details" selected={tab === "details"}>
            <DetailsTab {...formProps} offMarketLock={offMarketLock} />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="towers" selected={tab === "towers"}>
            <TowersTab {...childProps} />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="configurations" selected={tab === "configurations"}>
            <ConfigurationsTab {...childProps} canUpload={canUpload} />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="amenities" selected={tab === "amenities"}>
            <AmenitiesTab {...childProps} />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="specifications" selected={tab === "specifications"}>
            <SpecificationsTab {...childProps} />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="media" selected={tab === "media"}>
            <MediaTab
              project={project}
              canUpload={canUpload}
              onChanged={refresh}
              reportDirty={reportDirty}
              onGoToTab={setTab}
            />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="location" selected={tab === "location"}>
            <LocationTab {...formProps} {...childProps} />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="progress" selected={tab === "progress"}>
            <ProgressTab {...childProps} canUpload={canUpload} />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="payment-plans" selected={tab === "payment-plans"}>
            <PaymentPlansTab {...childProps} />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="faqs" selected={tab === "faqs"}>
            <FaqsTab project={project} reportDirty={reportDirty} />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="documents" selected={tab === "documents"}>
            <DocumentsTab
              {...formProps}
              project={project}
              canUpload={canUpload}
              onChanged={refresh}
              reportDirty={reportDirty}
            />
          </TabPanel>
          <TabPanel idPrefix="project" tabId="seo" selected={tab === "seo"}>
            <SeoTab
              {...formProps}
              project={project}
              canUpload={canUpload}
              reportDirty={reportDirty}
            />
          </TabPanel>
        </section>
        <PublishPanel
          project={project}
          actions={actions}
          dirty={dirty}
          canWrite={canWrite}
          canPublish={canPublish}
          canDelete={can("projects.delete")}
          onGoToTab={setTab}
        />
      </div>
      {leaveDialog}
    </>
  );
}

function LockIcon() {
  return (
    <svg
      aria-hidden="true"
      className="mr-1.5 inline-block align-[-2px]"
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

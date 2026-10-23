"use client";
/**
 * Progress (board NoirCmsProject, "Progress"): dated construction updates, for the whole project
 * or one tower, with a percentage and what changed. Draft updates stay in the CMS; publishing one
 * (while the project is live) tells the website to refresh (ARCHITECTURE §9,
 * `construction_update.published`). Each saved update has its progress photos under it
 * (ProgressPhotos.tsx, kept mounted while the update is edited); they upload and save straight
 * away.
 */
import { NumberField, Select, TextField, Textarea } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatCalendarDate } from "@/lib/dates";
import { UPDATE_STATE, keyOf, optionsOf, type UpdateState } from "@/lib/labels";
import { CollectionEditor } from "@/components/admin/CollectionEditor";
import { useCollection } from "@/components/admin/useCollection";
import { orNull, useReportDirty, type ChildTabProps, type ConstructionUpdate } from "./editorTypes";
import { ProgressPhotos } from "./ProgressPhotos";

interface UpdateDraft {
  update_date: string;
  tower_id: string;
  title: string;
  progress_percent: number | null;
  body: string;
  publish_state: UpdateState;
}

const toInput = (d: UpdateDraft): Schema<"ConstructionUpdateInput"> => ({
  update_date: d.update_date,
  tower_id: d.tower_id || null,
  title: d.title.trim(),
  progress_percent: d.progress_percent,
  body: orNull(d.body),
  publish_state: d.publish_state,
});

function validate(d: UpdateDraft) {
  const errors: Record<string, string> = {};
  if (!d.update_date) errors.update_date = "Enter the date of the update.";
  // Mirrors the API: an update reports what has happened (dates compared in India time).
  else if (d.update_date > todayInIndia()) {
    errors.update_date = "An update reports what has happened, so it can't be in the future.";
  }
  if (!d.title.trim()) errors.title = "Give the update a title, e.g. September 2026 progress.";
  if (d.progress_percent !== null && (d.progress_percent < 0 || d.progress_percent > 100)) {
    errors.progress_percent = "Enter a percentage from 0 to 100.";
  }
  return errors;
}

/** Today's date in India as yyyy-mm-dd, the default for a new update. */
function todayInIndia(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
}

export function ProgressTab({
  project,
  canWrite,
  canUpload,
  onChanged,
  reportDirty,
}: ChildTabProps & { canUpload: boolean }) {
  const id = project.id;
  const towers = project.towers ?? [];
  const towerName = (towerId: string | null | undefined) =>
    towers.find((t) => t.id === towerId)?.name ?? "Whole project";
  const updateLabel = (u: ConstructionUpdate) => `${formatCalendarDate(u.update_date)} update`;

  const updates = useCollection<ConstructionUpdate, UpdateDraft>({
    items: project.construction_updates ?? [],
    getId: (u) => u.id,
    getLabel: updateLabel,
    emptyDraft: () => ({
      update_date: todayInIndia(),
      tower_id: "",
      title: "",
      progress_percent: null,
      body: "",
      publish_state: "draft",
    }),
    toDraft: (u) => ({
      update_date: u.update_date,
      tower_id: u.tower_id ?? "",
      title: u.title,
      progress_percent: u.progress_percent ?? null,
      body: u.body ?? "",
      publish_state: u.publish_state ?? "draft",
    }),
    validate,
    create: (d) =>
      call(
        api.POST("/api/v1/admin/projects/{id}/construction-updates", {
          params: { path: { id } },
          body: toInput(d),
        }),
      ),
    update: (itemId, d) =>
      call(
        api.PATCH("/api/v1/admin/projects/{id}/construction-updates/{item_id}", {
          params: { path: { id, item_id: itemId } },
          body: toInput(d),
        }),
      ),
    remove: (itemId) =>
      call(
        api.DELETE("/api/v1/admin/projects/{id}/construction-updates/{item_id}", {
          params: { path: { id, item_id: itemId } },
        }),
      ),
    reorder: (ids) =>
      call(
        api.PUT("/api/v1/admin/projects/{id}/construction-updates/order", {
          params: { path: { id } },
          body: { ids },
        }),
      ),
    onChanged,
    noun: "update",
  });
  useReportDirty("progress", updates.dirty, reportDirty);

  return (
    <CollectionEditor
      id="progress"
      collection={updates}
      title="Construction updates"
      description="Updates are dated and shown tower by tower. Only published updates appear on the website."
      addLabel="+ Add update"
      emptyText="No construction updates yet."
      getId={(u) => u.id}
      getLabel={updateLabel}
      canWrite={canWrite}
      renderSummary={(u) => (
        <div className="flex flex-col gap-0.5">
          <span>
            <strong className="text-ivory">{formatCalendarDate(u.update_date)}</strong> ·{" "}
            {towerName(u.tower_id)}
            {u.progress_percent != null ? ` · ${u.progress_percent}% complete` : ""} ·{" "}
            <span className={u.publish_state === "published" ? "text-palm" : "text-muted"}>
              {UPDATE_STATE[u.publish_state ?? "draft"]}
            </span>
          </span>
          <span className="text-small text-ivory">{u.title}</span>
          {u.body ? (
            <span className="text-caption whitespace-pre-line text-muted">{u.body}</span>
          ) : null}
        </div>
      )}
      renderExtra={(u) => (
        // WHY outside the summary: Edit swaps the summary for the form; the photos (and any
        // upload still running) stay where they are.
        <ProgressPhotos
          update={u}
          canUpload={canUpload}
          onChanged={onChanged}
          reportDirty={reportDirty}
        />
      )}
      renderForm={(d, set, errors) => (
        <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
          <TextField
            label="Update date"
            type="date"
            required
            value={d.update_date}
            onChange={(e) => set({ update_date: e.target.value })}
            error={errors.update_date}
          />
          <Select
            label="Tower"
            value={d.tower_id}
            placeholder="Whole project"
            options={towers.map((t) => ({ value: t.id, label: t.name }))}
            onChange={(e) => set({ tower_id: e.target.value })}
            error={errors.tower_id}
          />
          <TextField
            label="Title"
            required
            maxLength={120}
            value={d.title}
            placeholder="[e.g. September 2026 progress]"
            onChange={(e) => set({ title: e.target.value })}
            error={errors.title}
          />
          <NumberField
            label="Progress (% complete)"
            suffix="%"
            value={d.progress_percent}
            onValueChange={(progress_percent) => set({ progress_percent })}
            error={errors.progress_percent}
            grouping={false}
          />
          <Textarea
            label="What changed"
            rows={3}
            maxLength={5000}
            value={d.body}
            placeholder="[e.g. Tower A: 18th-floor slab cast.]"
            onChange={(e) => set({ body: e.target.value })}
            error={errors.body}
            hint="Formatting: *bold* · _italic_ · - bullet"
            className="md:col-span-2"
          />
          <Select
            label="Status"
            value={d.publish_state}
            options={optionsOf(UPDATE_STATE)}
            onChange={(e) =>
              set({ publish_state: keyOf(UPDATE_STATE, e.target.value, d.publish_state) })
            }
            error={errors.publish_state}
            hint="Published updates show on the website once the project is live."
          />
          <p className="text-caption text-muted md:col-span-2">
            Progress photos are added under the update once it is saved. They are labelled
            &quot;Progress photo&quot; with the update&apos;s month.
          </p>
        </div>
      )}
    />
  );
}

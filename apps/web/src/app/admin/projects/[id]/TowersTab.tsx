"use client";
/**
 * Towers and phases: add, edit, remove and reorder. Each change saves straight away.
 * A phase with its own RERA registration gets its own number here (ARCHITECTURE §7: "Phase-wise
 * registrations show per tower/phase").
 */
import { NumberField, Select, TextField } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatCalendarDate } from "@/lib/dates";
import {
  TOWER_KIND,
  TOWER_STATUS,
  keyOf,
  optionsOf,
  type TowerKind,
  type TowerStatus,
} from "@/lib/labels";
import { CollectionEditor } from "@/components/admin/CollectionEditor";
import { useCollection } from "@/components/admin/useCollection";
import { orNull, useReportDirty, type ChildTabProps, type Tower } from "./editorTypes";

interface TowerDraft {
  name: string;
  kind: TowerKind;
  status: TowerStatus;
  floors: number | null;
  units_count: number | null;
  rera_number: string;
  possession_date: string;
}

const emptyDraft = (): TowerDraft => ({
  name: "",
  kind: "tower",
  status: "under_construction",
  floors: null,
  units_count: null,
  rera_number: "",
  possession_date: "",
});

const toDraft = (t: Tower): TowerDraft => ({
  name: t.name,
  kind: t.kind,
  status: t.status,
  floors: t.floors ?? null,
  units_count: t.units_count ?? null,
  rera_number: t.rera_number ?? "",
  possession_date: t.possession_date ?? "",
});

const toInput = (d: TowerDraft): Schema<"TowerInput"> => ({
  name: d.name.trim(),
  kind: d.kind,
  status: d.status,
  floors: d.floors,
  units_count: d.units_count,
  rera_number: orNull(d.rera_number),
  possession_date: orNull(d.possession_date),
});

export function TowersTab({ project, canWrite, onChanged, reportDirty }: ChildTabProps) {
  const id = project.id;
  const towers = useCollection<Tower, TowerDraft>({
    items: project.towers ?? [],
    getId: (t) => t.id,
    getLabel: (t) => t.name,
    emptyDraft,
    toDraft,
    validate: (d) => (d.name.trim() ? {} : { name: "Enter a name, e.g. Tower A." }),
    create: (d) =>
      call(
        api.POST("/api/v1/admin/projects/{id}/towers", {
          params: { path: { id } },
          body: toInput(d),
        }),
      ),
    update: (itemId, d) =>
      call(
        api.PATCH("/api/v1/admin/projects/{id}/towers/{item_id}", {
          params: { path: { id, item_id: itemId } },
          body: toInput(d),
        }),
      ),
    remove: (itemId) =>
      call(
        api.DELETE("/api/v1/admin/projects/{id}/towers/{item_id}", {
          params: { path: { id, item_id: itemId } },
        }),
      ),
    reorder: (ids) =>
      call(
        api.PUT("/api/v1/admin/projects/{id}/towers/order", {
          params: { path: { id } },
          body: { ids },
        }),
      ),
    onChanged,
    noun: "tower",
  });
  useReportDirty("towers", towers.dirty, reportDirty);

  return (
    <CollectionEditor
      id="towers"
      collection={towers}
      title="Towers and phases"
      description="The order here is the order on the website. Configurations and progress updates can point to a tower."
      addLabel="+ Add tower"
      emptyText="No towers or phases yet."
      getId={(t) => t.id}
      getLabel={(t) => t.name}
      canWrite={canWrite}
      renderSummary={(t) => (
        <span className="flex flex-col">
          <strong className="text-ivory">{t.name}</strong>
          <span className="text-caption text-muted">
            {[
              TOWER_KIND[t.kind],
              TOWER_STATUS[t.status],
              t.floors != null ? `${t.floors} floors` : null,
              t.units_count != null ? `${t.units_count} homes` : null,
              t.rera_number ? `RERA ${t.rera_number}` : null,
              t.possession_date ? `Possession ${formatCalendarDate(t.possession_date)}` : null,
              t.progress_percent != null ? `${t.progress_percent}% built` : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </span>
      )}
      renderForm={(d, set, errors) => (
        <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
          <TextField
            label="Name"
            required
            maxLength={60}
            value={d.name}
            placeholder="[e.g. Tower A]"
            onChange={(e) => set({ name: e.target.value })}
            error={errors.name}
          />
          <Select
            label="Kind"
            value={d.kind}
            options={optionsOf(TOWER_KIND)}
            onChange={(e) => set({ kind: keyOf(TOWER_KIND, e.target.value, d.kind) })}
            error={errors.kind}
          />
          <Select
            label="Status"
            value={d.status}
            options={optionsOf(TOWER_STATUS)}
            onChange={(e) => set({ status: keyOf(TOWER_STATUS, e.target.value, d.status) })}
            error={errors.status}
          />
          <NumberField
            label="Floors"
            value={d.floors}
            onValueChange={(floors) => set({ floors })}
            error={errors.floors}
            grouping={false}
          />
          <NumberField
            label="Homes (units)"
            value={d.units_count}
            onValueChange={(units_count) => set({ units_count })}
            error={errors.units_count}
          />
          <TextField
            label="RERA number (only if this phase has its own)"
            maxLength={60}
            value={d.rera_number}
            onChange={(e) => set({ rera_number: e.target.value })}
            error={errors.rera_number}
          />
          <TextField
            label="Possession date (as registered)"
            type="date"
            value={d.possession_date}
            onChange={(e) => set({ possession_date: e.target.value })}
            error={errors.possession_date}
          />
        </div>
      )}
    />
  );
}

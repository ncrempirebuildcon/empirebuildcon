"use client";
/**
 * Location advantages (board NoirCmsProject, "Location"): nearby places with an approximate road
 * distance and travel time. Add, edit, remove and reorder; each change saves straight away.
 *
 * Honest content: distances are always shown as approximate (≈) on the website; the CMS says so
 * under the list (LocationAdvantage: "Distances are approximate and shown as such").
 */
import { NumberField, Select, TextField } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { ADVANTAGE_KIND, keyOf, optionsOf, type AdvantageKind } from "@/lib/labels";
import { CollectionEditor } from "@/components/admin/CollectionEditor";
import { useCollection } from "@/components/admin/useCollection";
import { useReportDirty, type ChildTabProps, type LocationAdvantage } from "./editorTypes";

interface AdvantageDraft {
  label: string;
  kind: AdvantageKind;
  distance_km: number | null;
  travel_minutes: number | null;
}

const toInput = (d: AdvantageDraft): Schema<"LocationAdvantageInput"> => ({
  label: d.label.trim(),
  kind: d.kind,
  distance_km: d.distance_km,
  travel_minutes: d.travel_minutes,
});

/** "≈ 1.8 km · ≈ 6 min", the way the website shows it. */
export function distanceText(a: Pick<LocationAdvantage, "distance_km" | "travel_minutes">) {
  return [
    a.distance_km != null ? `≈ ${a.distance_km} km` : null,
    a.travel_minutes != null ? `≈ ${a.travel_minutes} min` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function AdvantagesSection({ project, canWrite, onChanged, reportDirty }: ChildTabProps) {
  const id = project.id;
  const advantages = useCollection<LocationAdvantage, AdvantageDraft>({
    items: project.location_advantages ?? [],
    getId: (a) => a.id,
    getLabel: (a) => a.label,
    emptyDraft: () => ({ label: "", kind: "transport", distance_km: null, travel_minutes: null }),
    toDraft: (a) => ({
      label: a.label,
      kind: a.kind,
      distance_km: a.distance_km ?? null,
      travel_minutes: a.travel_minutes ?? null,
    }),
    validate: (d) => (d.label.trim() ? {} : { label: "Name the place, e.g. Metro station." }),
    create: (d) =>
      call(
        api.POST("/api/v1/admin/projects/{id}/location-advantages", {
          params: { path: { id } },
          body: toInput(d),
        }),
      ),
    update: (itemId, d) =>
      call(
        api.PATCH("/api/v1/admin/projects/{id}/location-advantages/{item_id}", {
          params: { path: { id, item_id: itemId } },
          body: toInput(d),
        }),
      ),
    remove: (itemId) =>
      call(
        api.DELETE("/api/v1/admin/projects/{id}/location-advantages/{item_id}", {
          params: { path: { id, item_id: itemId } },
        }),
      ),
    reorder: (ids) =>
      call(
        api.PUT("/api/v1/admin/projects/{id}/location-advantages/order", {
          params: { path: { id } },
          body: { ids },
        }),
      ),
    onChanged,
    noun: "place",
  });
  useReportDirty("advantages", advantages.dirty, reportDirty);

  return (
    <CollectionEditor
      id="advantages"
      collection={advantages}
      title="Location advantages"
      addLabel="+ Add place"
      emptyText="No nearby places yet."
      getId={(a) => a.id}
      getLabel={(a) => a.label}
      canWrite={canWrite}
      footnote="Shown on the website as approximate road distances (≈)."
      renderSummary={(a) => (
        <span className="flex flex-wrap items-baseline gap-x-3">
          <strong className="text-ivory">{a.label}</strong>
          <span className="text-caption text-muted">
            {[ADVANTAGE_KIND[a.kind], distanceText(a)].filter(Boolean).join(" · ")}
          </span>
        </span>
      )}
      renderForm={(d, set, errors) => (
        <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
          <TextField
            label="Place"
            required
            maxLength={80}
            value={d.label}
            placeholder="[e.g. Nearest metro station]"
            onChange={(e) => set({ label: e.target.value })}
            error={errors.label}
          />
          <Select
            label="Kind"
            value={d.kind}
            options={optionsOf(ADVANTAGE_KIND)}
            onChange={(e) => set({ kind: keyOf(ADVANTAGE_KIND, e.target.value, d.kind) })}
            error={errors.kind}
          />
          <NumberField
            label="Road distance (km, approximate)"
            decimals={1}
            prefix="≈"
            suffix="km"
            value={d.distance_km}
            onValueChange={(distance_km) => set({ distance_km })}
            error={errors.distance_km}
          />
          <NumberField
            label="Travel time (minutes, approximate)"
            prefix="≈"
            suffix="min"
            value={d.travel_minutes}
            onValueChange={(travel_minutes) => set({ travel_minutes })}
            error={errors.travel_minutes}
          />
        </div>
      )}
    />
  );
}

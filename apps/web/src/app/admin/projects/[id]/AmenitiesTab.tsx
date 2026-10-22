"use client";
/**
 * Amenities: pick from the shared catalogue (Catalogue screen) and set the order the website
 * shows them in. Saved with "Save amenities" (PUT …/amenities replaces the ordered list).
 *
 * The catalogue holds generic options only; ticking one here is the claim that this project has
 * it, so the list starts empty for a new project (honest content, CODE_STYLE §7).
 */
import { useMemo, useState } from "react";
import Link from "next/link";
import { Alert, Button, Checkbox, ReorderList } from "@empire/ui";
import { api, call } from "@/lib/api";
import { AMENITY_CATEGORY, type AmenityCategory } from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import { CATALOGUE_PATH } from "@/lib/routes";
import { EmptyState, ErrorPanel, LoadingPanel, Panel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useReportDirty, type Amenity, type ChildTabProps } from "./editorTypes";

/** Every amenity in the catalogue (the list endpoint is paged, at most 100 a page). */
async function loadCatalogue(): Promise<Amenity[]> {
  const all: Amenity[] = [];
  for (let page = 1; page <= 20; page += 1) {
    const data = await call(
      api.GET("/api/v1/admin/amenities", { params: { query: { page, per_page: 100 } } }),
    );
    all.push(...data.items);
    if (page >= data.meta.pages) break;
  }
  return all;
}

export function AmenitiesTab({ project, canWrite, onChanged, reportDirty }: ChildTabProps) {
  const catalogue = useLoad("amenities", loadCatalogue);
  const savedIds = useMemo(() => (project.amenities ?? []).map((a) => a.id), [project.amenities]);
  // `chosen` is null until the user changes something, so a re-read project shows through.
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const ids = chosen ?? savedIds;
  const dirty = chosen !== null && chosen.join() !== savedIds.join();
  useReportDirty("amenities", dirty, reportDirty);

  const byId = new Map<string, Amenity>();
  for (const a of project.amenities ?? []) byId.set(a.id, a);
  for (const a of catalogue.data ?? []) byId.set(a.id, a);
  const chosenItems = ids.map((id) => byId.get(id)).filter((a): a is Amenity => a !== undefined);

  function toggle(id: string, on: boolean) {
    setSaved(false);
    setChosen(on ? [...ids.filter((x) => x !== id), id] : ids.filter((x) => x !== id));
  }

  async function save() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      await call(
        api.PUT("/api/v1/admin/projects/{id}/amenities", {
          params: { path: { id: project.id } },
          body: { amenity_ids: ids },
        }),
      );
      await onChanged();
      setChosen(null);
      setSaved(true);
    } catch (err) {
      setError(problemMessage(err, "Couldn't save the amenities."));
    } finally {
      setSaving(false);
    }
  }

  // Groups in the category order of the labels, so the list reads the same for every project.
  const groups = new Map<AmenityCategory, Amenity[]>();
  for (const category of Object.keys(AMENITY_CATEGORY) as AmenityCategory[]) {
    const items = (catalogue.data ?? []).filter((a) => a.category === category);
    if (items.length > 0) groups.set(category, items);
  }

  return (
    <div className="grid items-start gap-5 lg:grid-cols-2">
      <Panel
        id="amenities-chosen"
        title="On this project"
        description="Shown on the website in this order."
        actions={
          canWrite ? (
            <Button loading={saving} disabled={!dirty} onClick={save}>
              Save amenities
            </Button>
          ) : null
        }
      >
        {error ? <Alert tone="error">{error}</Alert> : null}
        {saved && !dirty ? <Alert tone="success">Amenities saved.</Alert> : null}
        {chosenItems.length === 0 ? (
          <EmptyState title="No amenities chosen yet." />
        ) : (
          <ReorderList
            label="Amenities in display order"
            items={chosenItems}
            getKey={(a) => a.id}
            getLabel={(a) => a.name}
            readOnly={!canWrite}
            disabled={saving}
            onReorder={(items) => {
              setSaved(false);
              setChosen(items.map((a) => a.id));
            }}
            renderItem={(a) => (
              <span className="flex flex-col">
                <strong className="text-ivory">{a.name}</strong>
                <span className="text-xs text-muted">{AMENITY_CATEGORY[a.category]}</span>
              </span>
            )}
          />
        )}
      </Panel>

      <Panel
        id="amenities-catalogue"
        title="Catalogue"
        description={
          <>
            Tick what this project has. Missing one? Add it under{" "}
            <Link href={CATALOGUE_PATH} className="underline">
              Catalogue
            </Link>
            .
          </>
        }
      >
        {catalogue.error ? (
          <ErrorPanel
            message={problemMessage(catalogue.error, "Couldn't load the amenities.")}
            onRetry={catalogue.reload}
          />
        ) : !catalogue.data ? (
          <LoadingPanel label="Loading amenities…" rows={3} />
        ) : catalogue.data.length === 0 ? (
          <EmptyState title="The amenity catalogue is empty." />
        ) : (
          <fieldset disabled={!canWrite} className="flex min-w-0 flex-col gap-4">
            <legend className="sr-only">Amenities in the catalogue</legend>
            {[...groups.entries()].map(([category, items]) => (
              <div key={category} className="flex flex-col gap-2">
                <h3 className="text-xs font-bold tracking-[0.08em] text-gold-400 uppercase">
                  {AMENITY_CATEGORY[category]}
                </h3>
                <div className="grid gap-2 sm:grid-cols-2">
                  {items.map((a) => (
                    <Checkbox
                      key={a.id}
                      checked={ids.includes(a.id)}
                      onChange={(e) => toggle(a.id, e.target.checked)}
                      label={a.name}
                    />
                  ))}
                </div>
              </div>
            ))}
          </fieldset>
        )}
      </Panel>
    </div>
  );
}

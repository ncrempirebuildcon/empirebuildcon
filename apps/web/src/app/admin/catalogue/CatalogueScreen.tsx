"use client";
/**
 * Catalogue (/admin/catalogue): the shared lists projects pick from — cities, localities (each in
 * one city) and amenities. Simple tables with add, edit and delete.
 *
 * Honest content: amenities here are generic options, not claims; a project claims one only when
 * an editor ticks it on that project (CODE_STYLE §7).
 * SECURITY: viewing needs projects.read and changes need projects.write; the API checks both.
 */
import { useState } from "react";
import { Chip, Select, TextField } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { AMENITY_CATEGORY, keyOf, optionsOf, type AmenityCategory } from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useCollection } from "@/components/admin/useCollection";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../session-context";
import { CatalogueSection } from "./CatalogueSection";

type City = Schema<"City">;
type Locality = Schema<"Locality">;
type Amenity = Schema<"Amenity">;

const DEFAULT_STATE = "Uttar Pradesh";
const noReorder = async () => undefined;

/** Reads every page of a paged catalogue list (100 a page). */
async function loadAll<T>(
  fetchPage: (page: number) => Promise<{ items: T[]; meta: { pages: number } }>,
): Promise<T[]> {
  const all: T[] = [];
  for (let page = 1; page <= 50; page += 1) {
    const data = await fetchPage(page);
    all.push(...data.items);
    if (page >= data.meta.pages) break;
  }
  return all;
}

const slugOrNothing = (slug: string) => (slug.trim() ? { slug: slug.trim() } : {});

export function CatalogueScreen() {
  const { can } = useAdminSession();
  const canWrite = can("projects.write");
  const cities = useLoad("cities", () =>
    loadAll((page) =>
      call(api.GET("/api/v1/admin/cities", { params: { query: { page, per_page: 100 } } })),
    ),
  );
  // WHY all localities here: deleting a city deletes its localities in the API, so a city
  // change must re-read them, and the delete dialog needs each city's locality count.
  const localities = useLoad("localities", () =>
    loadAll((page) =>
      call(api.GET("/api/v1/admin/localities", { params: { query: { page, per_page: 100 } } })),
    ),
  );
  const refreshCities = async () => {
    await Promise.all([cities.refresh(), localities.refresh()]);
  };

  return (
    <>
      <p className="max-w-[70ch] text-small text-muted">
        Cities, localities and amenities that projects choose from. Changes apply to every project
        that uses them.
      </p>
      {cities.error && !cities.data ? (
        <ErrorPanel
          message={problemMessage(cities.error, "Couldn't load the cities.")}
          onRetry={cities.reload}
        />
      ) : !cities.data ? (
        <LoadingPanel label="Loading the catalogue…" rows={6} />
      ) : (
        <>
          <CitiesSection
            cities={cities.data}
            localities={localities.data ?? []}
            canWrite={canWrite}
            onChanged={refreshCities}
          />
          <LocalitiesSection
            cities={cities.data}
            localities={localities.data ?? []}
            loading={localities.loading}
            loadError={
              localities.error
                ? problemMessage(localities.error, "Couldn't load the localities.")
                : null
            }
            canWrite={canWrite}
            onChanged={localities.refresh}
          />
          <AmenitiesSection canWrite={canWrite} />
        </>
      )}
    </>
  );
}

interface CityDraft {
  name: string;
  state: string;
  slug: string;
}

function CitiesSection({
  cities,
  localities,
  canWrite,
  onChanged,
}: {
  cities: City[];
  localities: Locality[];
  canWrite: boolean;
  onChanged: () => Promise<unknown>;
}) {
  const localityCount = (cityId: string) => localities.filter((l) => l.city_id === cityId).length;
  const toInput = (d: CityDraft): Schema<"CityInput"> => ({
    name: d.name.trim(),
    state: d.state.trim(),
    ...slugOrNothing(d.slug),
  });
  const collection = useCollection<City, CityDraft>({
    items: cities,
    getId: (c) => c.id,
    getLabel: (c) => c.name,
    emptyDraft: () => ({ name: "", state: DEFAULT_STATE, slug: "" }),
    toDraft: (c) => ({ name: c.name, state: c.state, slug: c.slug }),
    validate: (d) => ({
      ...(d.name.trim() ? {} : { name: "Enter the city's name." }),
      ...(d.state.trim() ? {} : { state: "Enter the state." }),
    }),
    create: (d) => call(api.POST("/api/v1/admin/cities", { body: toInput(d) })),
    update: (id, d) =>
      call(api.PATCH("/api/v1/admin/cities/{id}", { params: { path: { id } }, body: toInput(d) })),
    remove: (id) => call(api.DELETE("/api/v1/admin/cities/{id}", { params: { path: { id } } })),
    reorder: noReorder,
    onChanged,
    noun: "city",
  });

  return (
    <CatalogueSection
      id="cities"
      title="Cities"
      noun="city"
      collection={collection}
      canWrite={canWrite}
      getId={(c) => c.id}
      getLabel={(c) => c.name}
      emptyText="No cities yet."
      removeBody={(city) => {
        const count = localityCount(city.id);
        return count === 0
          ? "The city is deleted from the catalogue. A city that projects still use can't be deleted."
          : `The city and its ${count === 1 ? "locality" : `${count} localities`} are deleted ` +
              "from the catalogue. A city that projects still use can't be deleted.";
      }}
      columns={[
        { key: "name", header: "Name", rowHeader: true, cell: (c) => c.name },
        { key: "state", header: "State", cell: (c) => c.state },
        { key: "slug", header: "Web address", className: "text-muted", cell: (c) => `/${c.slug}` },
        {
          key: "projects",
          header: "Projects",
          className: "tabular-nums",
          cell: (c) => (c.project_count ?? 0).toLocaleString("en-IN"),
        },
      ]}
      renderForm={(d, set, errors) => (
        <div className="grid gap-x-5 gap-y-4 md:grid-cols-3">
          <TextField
            label="Name"
            required
            maxLength={80}
            value={d.name}
            onChange={(e) => set({ name: e.target.value })}
            error={errors.name}
          />
          <TextField
            label="State"
            required
            maxLength={60}
            value={d.state}
            onChange={(e) => set({ state: e.target.value })}
            error={errors.state}
          />
          <TextField
            label="Web address (slug)"
            maxLength={120}
            value={d.slug}
            onChange={(e) => set({ slug: e.target.value.toLowerCase() })}
            error={errors.slug}
            hint="Made from the name if left empty."
          />
        </div>
      )}
    />
  );
}

interface LocalityDraft {
  city_id: string;
  name: string;
  slug: string;
}

function LocalitiesSection({
  cities,
  localities,
  loading,
  loadError,
  canWrite,
  onChanged,
}: {
  cities: City[];
  localities: Locality[];
  loading: boolean;
  loadError: string | null;
  canWrite: boolean;
  onChanged: () => Promise<unknown>;
}) {
  const [chosenFilter, setCityFilter] = useState("");
  // A filter on a city that was just deleted falls back to "All cities".
  const cityFilter = cities.some((c) => c.id === chosenFilter) ? chosenFilter : "";
  const shown = cityFilter ? localities.filter((l) => l.city_id === cityFilter) : localities;
  const cityName = (id: string) => cities.find((c) => c.id === id)?.name ?? "—";
  const cityOptions = cities.map((c) => ({ value: c.id, label: c.name }));
  const toInput = (d: LocalityDraft): Schema<"LocalityInput"> => ({
    city_id: d.city_id,
    name: d.name.trim(),
    ...slugOrNothing(d.slug),
  });
  const collection = useCollection<Locality, LocalityDraft>({
    items: shown,
    getId: (l) => l.id,
    getLabel: (l) => l.name,
    emptyDraft: () => ({ city_id: cityFilter || (cities[0]?.id ?? ""), name: "", slug: "" }),
    toDraft: (l) => ({ city_id: l.city_id, name: l.name, slug: l.slug }),
    validate: (d) => ({
      ...(d.city_id ? {} : { city_id: "Choose the city this locality is in." }),
      ...(d.name.trim() ? {} : { name: "Enter the locality's name." }),
    }),
    create: (d) => call(api.POST("/api/v1/admin/localities", { body: toInput(d) })),
    update: (id, d) =>
      call(
        api.PATCH("/api/v1/admin/localities/{id}", { params: { path: { id } }, body: toInput(d) }),
      ),
    remove: (id) => call(api.DELETE("/api/v1/admin/localities/{id}", { params: { path: { id } } })),
    reorder: noReorder,
    onChanged,
    noun: "locality",
  });

  return (
    <CatalogueSection
      id="localities"
      title="Localities"
      description="Each locality belongs to one city; a project's locality must be in its city."
      noun="locality"
      collection={collection}
      canWrite={canWrite && cities.length > 0}
      getId={(l) => l.id}
      getLabel={(l) => l.name}
      loading={loading}
      emptyText={loadError ?? (cities.length === 0 ? "Add a city first." : "No localities yet.")}
      filters={
        <Select
          label="Show localities in"
          value={cityFilter}
          placeholder="All cities"
          options={cityOptions}
          onChange={(e) => setCityFilter(e.target.value)}
          className="max-w-xs"
        />
      }
      columns={[
        { key: "name", header: "Name", rowHeader: true, cell: (l) => l.name },
        { key: "city", header: "City", cell: (l) => cityName(l.city_id) },
        { key: "slug", header: "Web address", className: "text-muted", cell: (l) => `/${l.slug}` },
        {
          key: "projects",
          header: "Projects",
          className: "tabular-nums",
          cell: (l) => (l.project_count ?? 0).toLocaleString("en-IN"),
        },
      ]}
      renderForm={(d, set, errors) => (
        <div className="grid gap-x-5 gap-y-4 md:grid-cols-3">
          <Select
            label="City"
            required
            value={d.city_id}
            placeholder="Choose a city"
            options={cityOptions}
            onChange={(e) => set({ city_id: e.target.value })}
            error={errors.city_id}
          />
          <TextField
            label="Name"
            required
            maxLength={80}
            value={d.name}
            onChange={(e) => set({ name: e.target.value })}
            error={errors.name}
          />
          <TextField
            label="Web address (slug)"
            maxLength={120}
            value={d.slug}
            onChange={(e) => set({ slug: e.target.value.toLowerCase() })}
            error={errors.slug}
            hint="Made from the name if left empty. Unique within the city."
          />
        </div>
      )}
    />
  );
}

interface AmenityDraft {
  name: string;
  category: AmenityCategory;
  icon: string;
}

function AmenitiesSection({ canWrite }: { canWrite: boolean }) {
  const amenities = useLoad("amenities", () =>
    loadAll((page) =>
      call(api.GET("/api/v1/admin/amenities", { params: { query: { page, per_page: 100 } } })),
    ),
  );
  const toInput = (d: AmenityDraft): Schema<"AmenityInput"> => ({
    name: d.name.trim(),
    category: d.category,
    icon: d.icon.trim() || "amenity",
  });
  const collection = useCollection<Amenity, AmenityDraft>({
    items: amenities.data ?? [],
    getId: (a) => a.id,
    getLabel: (a) => a.name,
    emptyDraft: () => ({ name: "", category: "lifestyle", icon: "" }),
    toDraft: (a) => ({ name: a.name, category: a.category, icon: a.icon }),
    validate: (d) => (d.name.trim() ? {} : { name: "Enter the amenity's name." }),
    create: (d) => call(api.POST("/api/v1/admin/amenities", { body: toInput(d) })),
    update: (id, d) =>
      call(
        api.PATCH("/api/v1/admin/amenities/{id}", { params: { path: { id } }, body: toInput(d) }),
      ),
    remove: (id) => call(api.DELETE("/api/v1/admin/amenities/{id}", { params: { path: { id } } })),
    reorder: noReorder,
    onChanged: amenities.refresh,
    noun: "amenity",
  });

  return (
    <CatalogueSection
      id="amenities"
      title="Amenities"
      description="Generic options. A project shows an amenity only when an editor ticks it on that project."
      noun="amenity"
      collection={collection}
      canWrite={canWrite}
      getId={(a) => a.id}
      getLabel={(a) => a.name}
      loading={amenities.loading}
      emptyText={
        amenities.error
          ? problemMessage(amenities.error, "Couldn't load the amenities.")
          : "No amenities yet."
      }
      columns={[
        { key: "name", header: "Name", rowHeader: true, cell: (a) => a.name },
        {
          key: "category",
          header: "Category",
          cell: (a) => <Chip variant="draft">{AMENITY_CATEGORY[a.category]}</Chip>,
        },
        {
          key: "icon",
          header: "Icon key",
          className: "text-muted",
          cell: (a) => <code className="text-xs">{a.icon}</code>,
        },
      ]}
      renderForm={(d, set, errors) => (
        <div className="grid gap-x-5 gap-y-4 md:grid-cols-3">
          <TextField
            label="Name"
            required
            maxLength={80}
            value={d.name}
            onChange={(e) => set({ name: e.target.value })}
            error={errors.name}
          />
          <Select
            label="Category"
            value={d.category}
            options={optionsOf(AMENITY_CATEGORY)}
            onChange={(e) => set({ category: keyOf(AMENITY_CATEGORY, e.target.value, d.category) })}
            error={errors.category}
          />
          <TextField
            label="Icon key"
            maxLength={40}
            value={d.icon}
            onChange={(e) => set({ icon: e.target.value.toLowerCase() })}
            error={errors.icon}
            hint="Lowercase letters and hyphens, e.g. swimming-pool or gym."
          />
        </div>
      )}
    />
  );
}

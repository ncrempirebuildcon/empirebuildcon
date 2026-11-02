/**
 * The projects list with its filters, used by /projects and /cities/<slug> (task 5.3).
 * Server component: the API does the filtering, ordering (available first, sold out last;
 * off-market never) and paging (ARCHITECTURE §7).
 */
import Link from "next/link";
import { fetchPublicCities, fetchPublicProjects } from "@/lib/public/api";
import {
  type CatalogueFilters,
  hasFilters,
  PROJECT_SORTS,
  projectQuery,
} from "@/lib/public/catalogue";
import { ProjectCard } from "./Cards";
import { FilterForm, Pager, ResultCount } from "./ListControls";

export async function ProjectListing({
  path,
  filters,
  lockCity,
}: {
  path: string;
  filters: CatalogueFilters;
  /** On a city page the city is fixed by the address, so the form has no city field. */
  lockCity?: string;
}) {
  // On a city page the address fixes the city; a stray ?city= is ignored everywhere.
  const shown = lockCity ? { ...filters, city: undefined } : filters;
  const query = projectQuery({ ...shown, city: lockCity ?? shown.city });
  const [list, cities] = await Promise.all([fetchPublicProjects(query), fetchPublicCities()]);
  const { items, meta } = list;

  return (
    <div className="flex flex-col gap-6">
      <FilterForm
        action={path}
        filters={shown}
        cities={cities}
        sorts={PROJECT_SORTS}
        showCity={!lockCity}
      />
      <ResultCount total={meta.total} noun={["project", "projects"]} />
      {items.length > 0 ? <h2 className="sr-only">Projects</h2> : null}
      {items.length > 0 ? (
        <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((p) => (
            <li key={p.id} className="flex">
              <ProjectCard project={p} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex flex-col items-start gap-3 rounded-card border border-line bg-noir-800 p-6">
          <h2 className="font-display text-h3 font-semibold">
            {meta.total > 0
              ? "This page is past the end of the list"
              : hasFilters(shown)
                ? "No projects match these filters"
                : "No projects to show yet"}
          </h2>
          <p className="text-body">
            {hasFilters(shown)
              ? "Try another city or budget, or tell us what you need and we'll call you when something fits."
              : "New projects appear here as soon as they are registered and published."}
          </p>
          <div className="flex flex-wrap gap-4">
            {hasFilters(shown) ? (
              <Link href={path} className="inline-flex min-h-11 items-center font-semibold">
                Clear filters
              </Link>
            ) : null}
            <Link href="/contact" className="inline-flex min-h-11 items-center font-semibold">
              Contact us
            </Link>
          </div>
        </div>
      )}
      <Pager path={path} filters={shown} page={meta.page} pages={meta.pages} noun="projects" />
      <p className="text-caption text-muted">
        Prices exclude GST, stamp duty and registration. Images are labelled for what they are:
        artist&apos;s impression, actual photo or progress photo.
      </p>
    </div>
  );
}

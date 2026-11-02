/**
 * /properties: every home type (configuration) across published projects (board
 * NoirProperties; task 5.3). Carpet area first, the starting price and the project's UP-RERA
 * number on every card.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { PropertyCard } from "@/components/catalogue/Cards";
import { Breadcrumbs, FilterForm, Pager, ResultCount } from "@/components/catalogue/ListControls";
import { fetchPublicCities, fetchPublicProperties } from "@/lib/public/api";
import {
  hasFilters,
  parseFilters,
  PROPERTY_SORTS,
  propertyQuery,
  type SearchParams,
} from "@/lib/public/catalogue";

export const metadata: Metadata = { title: "Properties" };

export default async function PropertiesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const filters = parseFilters(await searchParams, PROPERTY_SORTS);
  const [list, cities] = await Promise.all([
    fetchPublicProperties(propertyQuery(filters)),
    fetchPublicCities(),
  ]);
  const { items, meta } = list;
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
      <Breadcrumbs items={[{ href: "/", label: "Home" }, { label: "Properties" }]} />
      <header className="flex flex-col gap-3">
        <p className="font-display text-eyebrow tracking-[0.28em] text-gold-400 uppercase">
          Properties
        </p>
        <h1 className="font-display text-[clamp(32px,6vw,58px)] leading-tight font-semibold text-balance text-metallic">
          Homes by size and budget
        </h1>
        <p className="max-w-[42em] text-lede text-body">
          Every home type across Empire&apos;s projects, with carpet area first, the starting price
          and the project&apos;s UP-RERA number.
        </p>
      </header>
      <FilterForm
        action="/properties"
        filters={filters}
        cities={cities}
        sorts={PROPERTY_SORTS}
        showSearch={false}
      />
      <ResultCount total={meta.total} noun={["home", "homes"]} />
      {items.length > 0 ? (
        <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((p) => (
            <li key={p.id} className="flex">
              <PropertyCard property={p} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex flex-col items-start gap-3 rounded-card border border-line bg-noir-800 p-6">
          <h2 className="font-display text-h3 font-semibold">
            {hasFilters(filters) ? "No homes match these filters" : "No homes to show yet"}
          </h2>
          <p className="text-body">
            Try another budget or BHK, or tell us what you are looking for and we&apos;ll call you
            when a home fits.
          </p>
          <div className="flex flex-wrap gap-4">
            {hasFilters(filters) ? (
              <Link href="/properties" className="inline-flex min-h-11 items-center font-semibold">
                Clear filters
              </Link>
            ) : null}
            <Link href="/contact" className="inline-flex min-h-11 items-center font-semibold">
              Contact us
            </Link>
          </div>
        </div>
      )}
      <Pager
        path="/properties"
        filters={filters}
        page={meta.page}
        pages={meta.pages}
        noun="homes"
      />
      <p className="text-caption text-muted">
        Carpet area as registered with UP-RERA. Prices are starting base prices and exclude GST,
        stamp duty and registration.
      </p>
    </div>
  );
}

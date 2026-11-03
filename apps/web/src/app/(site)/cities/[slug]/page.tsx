/**
 * /cities/<slug>: one city's published projects (task 5.3, D-041). The city must be in
 * /public/cities (at least one published, visible project); any other slug is a 404, so the
 * site never shows an empty page for a made-up city.
 */
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/catalogue/ListControls";
import { ProjectListing } from "@/components/catalogue/ProjectListing";
import { fetchPublicCities } from "@/lib/public/api";
import { cityPath, parseFilters, PROJECT_SORTS, type SearchParams } from "@/lib/public/catalogue";

async function findCity(slug: string) {
  const cities = await fetchPublicCities();
  return cities.find((c) => c.slug === slug) ?? null;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const city = await findCity((await params).slug);
  return { title: city ? `Projects in ${city.name}` : "City not found" };
}

export default async function CityPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<SearchParams>;
}) {
  const { slug } = await params;
  const city = await findCity(slug);
  if (!city) notFound();
  const filters = parseFilters(await searchParams, PROJECT_SORTS);
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
      <Breadcrumbs
        items={[
          { href: "/", label: "Home" },
          { href: "/projects", label: "Projects" },
          { label: city.name },
        ]}
      />
      <header className="flex flex-col gap-3">
        <p className="font-display text-eyebrow tracking-[0.28em] text-gold-400 uppercase">
          {city.state}
        </p>
        <h1 className="font-display text-[clamp(32px,6vw,58px)] leading-tight font-semibold text-balance text-metallic">
          Projects in {city.name}
        </h1>
      </header>
      <ProjectListing path={cityPath(city.slug)} filters={filters} lockCity={city.slug} />
    </div>
  );
}

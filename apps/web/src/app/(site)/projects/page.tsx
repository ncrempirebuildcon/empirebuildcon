/**
 * /projects: every published project, filterable in the URL (board NoirProjects; task 5.3).
 */
import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/catalogue/ListControls";
import { ProjectListing } from "@/components/catalogue/ProjectListing";
import { parseFilters, PROJECT_SORTS, type SearchParams } from "@/lib/public/catalogue";

export const metadata: Metadata = { title: "Projects" };

export default async function ProjectsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const filters = parseFilters(await searchParams, PROJECT_SORTS);
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
      <Breadcrumbs items={[{ href: "/", label: "Home" }, { label: "Projects" }]} />
      <header className="flex flex-col gap-3">
        <p className="font-display text-eyebrow tracking-[0.28em] text-gold-400 uppercase">
          Our projects
        </p>
        <h1 className="font-display text-[clamp(32px,6vw,58px)] leading-tight font-semibold text-balance text-metallic">
          Projects in Uttar Pradesh
        </h1>
        <p className="max-w-[42em] text-lede text-body">
          Every card shows the price, the homes on offer, possession and the UP-RERA number.
        </p>
      </header>
      <ProjectListing path="/projects" filters={filters} />
    </div>
  );
}

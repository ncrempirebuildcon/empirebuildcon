/**
 * Project and property cards for the public lists (DESIGN_SYSTEM §8 "Project card",
 * "Property card"; boards NoirProjects and NoirProperties; task 5.3).
 *
 * - The card is an `<article>` with its title as a heading link. It is not one big link,
 *   because it also holds the external "Verify" link to up-rera.in, and links can't nest.
 * - The image has its honest label (D-033) and the SAMPLE badge for sample rows outside
 *   production (D-015). A card without a cover shows a plain panel, not a stock photo.
 */
import Link from "next/link";
import type { components } from "@empire/api-client";
import { PublicImage } from "@/components/media/PublicImage";
import { bhkLabel, formatMonthYear, projectPath, propertyPath } from "@/lib/public/catalogue";
import { PROPERTY_TYPE } from "@/lib/labels";
import { ReraBlock } from "./ReraBlock";
import { AreaText, PriceText, ProjectStatusChip, SampleChip, SoldOutChip } from "./Facts";

type ProjectSummary = components["schemas"]["PublicProjectSummary"];
type PropertySummary = components["schemas"]["PublicPropertySummary"];
type Media = components["schemas"]["PublicMedia"];

function CardImage({
  media,
  alt,
  isSample,
}: {
  media?: Media | null;
  alt: string;
  isSample?: boolean;
}) {
  if (!media) {
    return (
      <div
        className="grid aspect-[4/3] place-items-center rounded-t-[999px] bg-noir-700 text-caption text-muted"
        aria-hidden="true"
      >
        Photos coming soon
      </div>
    );
  }
  return (
    <PublicImage
      src={media.url}
      alt={media.alt_text || alt}
      label={media.label}
      labelMonth={media.label_month}
      isSample={isSample || media.is_sample}
      width={media.width ?? 800}
      height={media.height ?? 600}
      sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
      containerClassName="block w-full overflow-hidden rounded-t-[999px] rounded-b-[10px]"
      className="aspect-[4/3] w-full object-cover"
    />
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
        {label}
      </dt>
      <dd className="text-small text-body">{children}</dd>
    </div>
  );
}

export function ProjectCard({ project }: { project: ProjectSummary }) {
  const href = projectPath(project.slug);
  const place = [project.locality?.name, project.city?.name].filter(Boolean).join(", ");
  const possession = formatMonthYear(project.possession_date);
  return (
    <article
      className="flex flex-col overflow-hidden rounded-card border border-gold-line bg-noir-800"
      data-testid="project-card"
    >
      <CardImage media={project.cover} alt={project.name} isSample={project.is_sample} />
      <div className="flex flex-1 flex-col gap-3 p-5">
        <div className="flex flex-wrap gap-2">
          <ProjectStatusChip status={project.status} />
          <SoldOutChip salesStatus={project.sales_status} />
          <SampleChip isSample={project.is_sample} />
        </div>
        <h3 className="font-display text-xl font-semibold">
          <Link href={href} className="text-ivory hover:text-gold-300">
            {project.name}
          </Link>
        </h3>
        {place ? <p className="text-small text-muted">{place}</p> : null}
        <dl className="grid grid-cols-2 gap-3">
          {project.configuration_labels.length > 0 ? (
            <Fact label="Homes">{project.configuration_labels.join(", ")}</Fact>
          ) : null}
          {possession ? <Fact label="Possession">{possession}</Fact> : null}
        </dl>
        <PriceText price={project.price} />
        <ReraBlock rera={project.rera} projectName={project.name} variant="line" />
        <Link
          href={href}
          className="mt-auto inline-flex min-h-11 items-center font-semibold"
          aria-label={`View project ${project.name}`}
        >
          View project →
        </Link>
      </div>
    </article>
  );
}

export function PropertyCard({ property }: { property: PropertySummary }) {
  const href = propertyPath(property.project.slug, property.slug);
  const kind = PROPERTY_TYPE[property.property_type as keyof typeof PROPERTY_TYPE] ?? "Home";
  const title = [bhkLabel(property.bhk), kind.toLowerCase()].filter(Boolean).join(" ");
  const place = [property.project.locality?.name, property.project.city?.name]
    .filter(Boolean)
    .join(", ");
  return (
    <article
      className="flex flex-col overflow-hidden rounded-card border border-gold-line bg-noir-800"
      data-testid="property-card"
    >
      <CardImage media={property.cover} alt={property.name} isSample={property.is_sample} />
      <div className="flex flex-1 flex-col gap-3 p-5">
        <div className="flex flex-wrap gap-2">
          <ProjectStatusChip status={property.project.status} />
          <SoldOutChip salesStatus={property.sales_status} />
          <SampleChip isSample={property.is_sample} />
        </div>
        <h3 className="font-display text-xl font-semibold">
          <Link href={href} className="text-ivory hover:text-gold-300">
            {property.name}
          </Link>
        </h3>
        <p className="text-small text-muted">
          {title ? `${title.charAt(0).toUpperCase()}${title.slice(1)} · ` : ""}
          {property.project.name}
          {place ? ` · ${place}` : ""}
        </p>
        <dl className="grid gap-3">
          <Fact label="Area">
            <AreaText area={property.area} />
          </Fact>
        </dl>
        <PriceText price={property.price} />
        {property.project.rera ? (
          <ReraBlock
            rera={property.project.rera}
            projectName={property.project.name}
            variant="line"
          />
        ) : null}
        <Link
          href={href}
          className="mt-auto inline-flex min-h-11 items-center font-semibold"
          aria-label={`View home ${property.name} in ${property.project.name}`}
        >
          View home →
        </Link>
      </div>
    </article>
  );
}

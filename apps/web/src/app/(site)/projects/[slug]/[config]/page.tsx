/**
 * /projects/<slug>/<config-slug>: one home type ("property") of a published project (boards
 * NoirProperty, NoirMobileProperty; task 5.3, D-041).
 *
 * COMPLIANCE: the project's RERA block (number, QR, up-rera.in), carpet area first in both
 * units, the price with its tax note ("price on request" hides numbers), honest labels on the
 * floor plan. A sold-out home says so plainly and points to the homes still available; there is
 * no "only N left" wording (D-035).
 */
import type { Metadata } from "next";
import Link from "next/link";
import { PublicImage } from "@/components/media/PublicImage";
import { Breadcrumbs } from "@/components/catalogue/ListControls";
import { ReraBlock } from "@/components/catalogue/ReraBlock";
import {
  AreaText,
  PriceText,
  priceText,
  ProjectStatusChip,
  SampleChip,
  SoldOutChip,
} from "@/components/catalogue/Facts";
import { configurationTitle, Section } from "@/components/catalogue/ProjectSections";
import { fetchPublicProject, fetchPublicProperty } from "@/lib/public/api";
import { formatMonthYear, projectPath, propertyPath } from "@/lib/public/catalogue";

type Params = { params: Promise<{ slug: string; config: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug, config } = await params;
  const property = await fetchPublicProperty(slug, config);
  return { title: `${configurationTitle(property)} · ${property.project.name}` };
}

export default async function PropertyPage({ params }: Params) {
  const { slug, config } = await params;
  const [property, project] = await Promise.all([
    fetchPublicProperty(slug, config),
    fetchPublicProject(slug),
  ]);
  const title = configurationTitle(property);
  const place = [project.locality?.name, project.city?.name, project.location.state]
    .filter(Boolean)
    .join(", ");
  const possession = formatMonthYear(project.possession_date);
  const soldOut = property.sales_status === "sold_out";
  const others = [...project.configurations]
    .filter((c) => c.slug !== property.slug)
    .sort((a, b) => {
      // Available homes first, as on the lists (ARCHITECTURE §7).
      const rank = (s: string) => (s === "sold_out" ? 1 : 0);
      return rank(a.sales_status) - rank(b.sales_status) || a.sort_order - b.sort_order;
    });
  const enquire = `/contact?project=${encodeURIComponent(project.slug)}&home=${encodeURIComponent(property.slug)}`;
  const plan = property.floor_plans[0];

  return (
    <article className="mx-auto flex max-w-7xl flex-col gap-10 px-4 py-8 sm:px-6 lg:px-8">
      <Breadcrumbs
        items={[
          { href: "/", label: "Home" },
          { href: "/properties", label: "Properties" },
          { href: projectPath(project.slug), label: project.name },
          { label: title },
        ]}
      />

      <header className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          <ProjectStatusChip status={project.status} />
          <SoldOutChip salesStatus={property.sales_status} />
          <SampleChip isSample={property.is_sample} />
        </div>
        <h1 className="font-display text-[clamp(32px,6vw,58px)] leading-tight font-semibold text-balance text-metallic">
          {title}
        </h1>
        <p className="text-lede text-body">
          <Link href={projectPath(project.slug)} className="underline underline-offset-4">
            {project.name}
          </Link>
          {place ? <span className="text-muted"> · {place}</span> : null}
        </p>
        <ReraBlock rera={project.rera} projectName={project.name} variant="line" />
      </header>

      <dl
        className="grid grid-cols-2 gap-4 rounded-card border border-gold-line bg-noir-800 p-5 md:grid-cols-4"
        data-testid="key-facts"
      >
        <div className="flex flex-col gap-1">
          <dt className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
            Carpet area
          </dt>
          <dd>
            <AreaText area={property.area} />
            <span className="block text-caption text-muted">as per RERA</span>
          </dd>
        </div>
        <div className="flex flex-col gap-1">
          <dt className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
            Price from
          </dt>
          <dd>
            <PriceText price={property.price} size="lg" />
          </dd>
        </div>
        {possession ? (
          <div className="flex flex-col gap-1">
            <dt className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
              Possession
            </dt>
            <dd className="text-body">
              {possession}
              <span className="block text-caption text-muted">date registered with RERA</span>
            </dd>
          </div>
        ) : null}
        <div className="flex flex-col gap-1">
          <dt className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
            Availability
          </dt>
          <dd className="text-body">{soldOut ? "Sold out" : "Available"}</dd>
        </div>
      </dl>

      <ReraBlock rera={project.rera} towers={project.towers} projectName={project.name} />

      <div className="grid grid-cols-1 gap-12 lg:grid-cols-[1fr_320px]">
        <div className="flex min-w-0 flex-col gap-14">
          {plan ? (
            <Section id="floor-plan" title="Floor plan">
              {plan.kind === "image" ? (
                <div className="rounded-tile bg-ivory-tile p-3">
                  <PublicImage
                    src={plan.url}
                    alt={plan.alt_text || `${title} floor plan`}
                    label={plan.label}
                    isSample={plan.is_sample}
                    width={plan.width ?? 1200}
                    height={plan.height ?? 900}
                    sizes="(max-width: 1024px) 100vw, 60vw"
                    containerClassName="block w-full"
                    className="h-auto w-full object-contain"
                  />
                </div>
              ) : (
                <a
                  href={plan.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex min-h-11 items-center self-start font-semibold"
                >
                  Download floor plan (PDF)<span className="sr-only"> (opens in a new tab)</span>
                </a>
              )}
              <p className="text-caption text-muted">
                Floor plans are indicative and not to scale. Carpet area is as registered with{" "}
                {project.rera.authority}.
              </p>
            </Section>
          ) : null}

          {others.length > 0 ? (
            <Section id="other-homes" title={`Other homes in ${project.name}`}>
              <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {others.map((c) => (
                  <li
                    key={c.id}
                    className="flex flex-col gap-1 rounded-card border border-line bg-noir-800 p-4"
                  >
                    <Link
                      href={propertyPath(project.slug, c.slug)}
                      className="inline-flex min-h-11 items-center font-semibold"
                    >
                      {configurationTitle(c)}
                    </Link>
                    <span className="text-small">
                      <AreaText area={c.area} />
                    </span>
                    <span className="text-small font-bold text-gold-300">{priceText(c.price)}</span>
                    {c.sales_status === "sold_out" ? (
                      <span>
                        <SoldOutChip salesStatus="sold_out" />
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          <p className="text-caption text-muted">
            Prices are starting base prices and may vary by floor and view as shown in the cost
            sheet. This page is not an offer and makes no promise of returns.
          </p>
        </div>

        <aside aria-label={`Ask about ${title}`} className="lg:sticky lg:top-24 lg:self-start">
          <div className="flex flex-col gap-3 rounded-card border border-gold-line-strong bg-noir-800 p-5">
            {soldOut ? (
              <>
                <h2 className="font-display text-h3 font-semibold">Every {title} is booked</h2>
                <p className="text-small text-body">
                  We no longer take enquiries for this home type.
                </p>
                <Link
                  href={projectPath(project.slug)}
                  className="inline-flex min-h-11 items-center justify-center rounded-pill border border-gold-500 px-5 font-semibold text-gold-300"
                >
                  See all homes in {project.name}
                </Link>
              </>
            ) : (
              <>
                <h2 className="font-display text-h3 font-semibold">Ask about this home</h2>
                <p className="text-small text-body">
                  {title} · {priceText(property.price)}
                </p>
                <Link
                  href={enquire}
                  className="inline-flex min-h-11 items-center justify-center rounded-pill bg-gold-500 px-5 font-extrabold text-noir-900 hover:bg-gold-400 hover:text-noir-900"
                >
                  Enquire
                </Link>
                <Link
                  href={`${enquire}&want=visit`}
                  className="inline-flex min-h-11 items-center justify-center rounded-pill border border-gold-500 px-5 font-semibold text-gold-300"
                >
                  Book a site visit
                </Link>
              </>
            )}
          </div>
        </aside>
      </div>
    </article>
  );
}

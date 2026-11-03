/**
 * /projects/<slug>: one published project (boards NoirProject, NoirMobileProject; task 5.3).
 *
 * COMPLIANCE (AGENTS.md "Honest content", D-002): the RERA block (number, QR, up-rera.in) is
 * near the top and again in the Documents section; prices carry the tax note and "price on
 * request" hides numbers; carpet area comes first; every image has its honest label. An
 * off-market, draft or unknown project is a 404 (the API returns 404; the data layer turns it
 * into `notFound()`).
 *
 * The enquiry and site-visit buttons go to the contact page until 5.4 adds the forms.
 */
import type { Metadata } from "next";
import { FormattedText } from "@empire/ui";
import { PublicImage } from "@/components/media/PublicImage";
import { Breadcrumbs } from "@/components/catalogue/ListControls";
import { ReraBlock } from "@/components/catalogue/ReraBlock";
import {
  PriceText,
  ProjectStatusChip,
  SampleChip,
  SoldOutChip,
} from "@/components/catalogue/Facts";
import ProjectMap from "@/components/catalogue/ProjectMap";
import { LeadPanel } from "@/components/leads/LeadPanel";
import {
  Amenities,
  ConfigurationsTable,
  Documents,
  Faqs,
  FloorPlans,
  Gallery,
  LocationAdvantages,
  PaymentPlans,
  Progress,
  Section,
  Specifications,
  Videos,
} from "@/components/catalogue/ProjectSections";
import { fetchPublicProject } from "@/lib/public/api";
import { cityPath, directionsUrl, formatMonthYear, projectPath } from "@/lib/public/catalogue";
import { faqLd, pageMetadata, projectLd } from "@/lib/public/seo";
import { JsonLd } from "@/components/JsonLd";

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const project = await fetchPublicProject((await params).slug);
  return pageMetadata({
    title: project.name,
    path: projectPath(project.slug),
    seo: project.seo,
    fallbackDescriptions: [project.tagline, project.description],
    image: project.cover,
  });
}

export default async function ProjectPage({ params }: Params) {
  const { slug } = await params;
  const project = await fetchPublicProject(slug);
  const place = [project.locality?.name, project.city?.name, project.location.state]
    .filter(Boolean)
    .join(", ");
  const possession = formatMonthYear(project.possession_date);
  const directions = directionsUrl(project.location);
  const address = [project.location.address_line, project.location.pincode]
    .filter(Boolean)
    .join(" ");
  // A gated brochure is given by the form below (#brochure); an open one is a plain link.
  const brochureHref = project.brochure_gated ? "#brochure" : (project.brochure?.url ?? null);
  const path = `/projects/${project.slug}`;

  const nav = [
    { id: "overview", label: "Overview", show: Boolean(project.description || project.tagline) },
    { id: "prices", label: "Prices & plans", show: project.configurations.length > 0 },
    { id: "gallery", label: "Gallery", show: project.gallery.length + project.videos.length > 0 },
    {
      id: "amenities",
      label: "Amenities",
      show: project.amenities.length + project.specifications.length > 0,
    },
    {
      id: "location",
      label: "Location",
      show: Boolean(directions || address || project.location_advantages.length),
    },
    {
      id: "progress",
      label: "Progress",
      show:
        project.construction_updates.length > 0 ||
        project.towers.some((t) => t.progress_percent != null),
    },
    { id: "payment", label: "Payment plan", show: project.payment_plans.some((p) => p.is_visible) },
    { id: "documents", label: "Documents & RERA", show: true },
    { id: "faqs", label: "FAQs", show: project.faqs.some((f) => f.is_visible) },
  ].filter((n) => n.show);

  const hasPin =
    project.location.lat !== null &&
    project.location.lat !== undefined &&
    project.location.lng !== null &&
    project.location.lng !== undefined;

  return (
    <article className="mx-auto flex max-w-7xl flex-col gap-10 px-4 py-8 sm:px-6 lg:px-8">
      <JsonLd data={projectLd(project, path)} />
      {project.is_sample ? null : <JsonLd data={faqLd(project.faqs)} />}
      <Breadcrumbs
        structuredData={!project.is_sample}
        items={[
          { href: "/", label: "Home" },
          { href: "/projects", label: "Projects" },
          ...(project.city
            ? [{ href: cityPath(project.city.slug), label: project.city.name }]
            : []),
          { label: project.name },
        ]}
      />

      <header className="grid grid-cols-1 gap-8 lg:grid-cols-[3fr_2fr] lg:items-end">
        {project.cover ? (
          <PublicImage
            src={project.cover.url}
            alt={project.cover.alt_text || project.name}
            label={project.cover.label}
            labelMonth={project.cover.label_month}
            isSample={project.cover.is_sample}
            width={project.cover.width ?? 1600}
            height={project.cover.height ?? 1000}
            sizes="(max-width: 1024px) 100vw, 60vw"
            priority
            containerClassName="block w-full overflow-hidden rounded-t-[999px] rounded-b-[18px]"
            className="aspect-[4/3] w-full object-cover"
          />
        ) : null}
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            <ProjectStatusChip status={project.status} />
            <SoldOutChip salesStatus={project.sales_status} />
            <SampleChip isSample={project.is_sample} />
          </div>
          <h1 className="font-display text-[clamp(36px,6vw,64px)] leading-tight font-semibold text-balance text-metallic">
            {project.name}
          </h1>
          {project.tagline ? <p className="text-lede text-body">{project.tagline}</p> : null}
          {place ? <p className="text-small text-muted">{place}</p> : null}
          <ReraBlock rera={project.rera} projectName={project.name} variant="line" />
        </div>
      </header>

      <dl
        className="grid grid-cols-2 gap-4 rounded-card border border-gold-line bg-noir-800 p-5 md:grid-cols-4"
        data-testid="key-facts"
      >
        <div className="flex flex-col gap-1">
          <dt className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
            Price
          </dt>
          <dd>
            <PriceText price={project.price} size="lg" />
          </dd>
        </div>
        {project.configuration_labels.length > 0 ? (
          <div className="flex flex-col gap-1">
            <dt className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
              Homes
            </dt>
            <dd className="text-body">{project.configuration_labels.join(", ")}</dd>
          </div>
        ) : null}
        {possession ? (
          <div className="flex flex-col gap-1">
            <dt className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
              Possession
            </dt>
            <dd className="text-body">{possession}</dd>
          </div>
        ) : null}
        {project.towers.length > 0 ? (
          <div className="flex flex-col gap-1">
            <dt className="text-caption font-semibold tracking-[0.08em] text-gold-400 uppercase">
              Towers
            </dt>
            <dd className="text-body">{project.towers.length}</dd>
          </div>
        ) : null}
      </dl>

      <ReraBlock rera={project.rera} towers={project.towers} projectName={project.name} />

      <nav
        aria-label="On this page"
        className="sticky top-16 z-10 -mx-4 overflow-x-auto bg-noir-900/95 px-4 py-2"
      >
        <ul className="flex gap-1">
          {nav.map((n) => (
            <li key={n.id}>
              <a
                href={`#${n.id}`}
                className="inline-flex min-h-11 items-center whitespace-nowrap rounded-pill px-3 text-small"
              >
                {n.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="grid grid-cols-1 gap-12 lg:grid-cols-[1fr_320px]">
        <div className="flex min-w-0 flex-col gap-14">
          {project.description || project.tagline ? (
            <Section id="overview" title="Overview">
              {project.description ? (
                <FormattedText text={project.description} />
              ) : (
                <p>{project.tagline}</p>
              )}
            </Section>
          ) : null}

          {project.configurations.length > 0 ? (
            <Section id="prices" title="Prices & floor plans">
              <ConfigurationsTable
                projectSlug={project.slug}
                configurations={project.configurations}
              />
              <FloorPlans projectSlug={project.slug} configurations={project.configurations} />
            </Section>
          ) : null}

          {project.gallery.length + project.videos.length > 0 ? (
            <Section id="gallery" title="Gallery">
              <Gallery items={project.gallery} projectName={project.name} />
              <Videos items={project.videos} projectName={project.name} />
            </Section>
          ) : null}

          {project.amenities.length + project.specifications.length > 0 ? (
            <Section id="amenities" title="Amenities & specifications">
              <Amenities items={project.amenities} />
              <Specifications items={project.specifications} />
            </Section>
          ) : null}

          {directions || address || project.location_advantages.length > 0 ? (
            <Section id="location" title="Location">
              {address ? <p className="text-body">{address}</p> : null}
              {directions ? (
                <a
                  href={directions}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex min-h-11 items-center self-start font-semibold"
                >
                  Get directions<span className="sr-only"> (opens Google Maps in a new tab)</span>
                </a>
              ) : null}
              {hasPin && directions ? (
                <ProjectMap
                  lat={project.location.lat as number}
                  lng={project.location.lng as number}
                  name={project.name}
                  address={address || null}
                  reraNumber={project.rera.number ?? null}
                  directionsUrl={directions}
                />
              ) : null}
              <LocationAdvantages items={project.location_advantages} />
              {project.location_advantages.length > 0 ? (
                <p className="text-caption text-muted">Approximate road distances.</p>
              ) : null}
            </Section>
          ) : null}

          {nav.some((n) => n.id === "progress") ? (
            <Section id="progress" title="Construction progress">
              <Progress project={project} />
            </Section>
          ) : null}

          {project.payment_plans.some((p) => p.is_visible) ? (
            <Section id="payment" title="Payment plan">
              <PaymentPlans plans={project.payment_plans} />
            </Section>
          ) : null}

          <Section id="documents" title="Documents & RERA">
            <ReraBlock rera={project.rera} towers={project.towers} projectName={project.name} />
            <Documents project={project} brochureHref={brochureHref} />
            <p className="text-small text-body">
              Pay only into the project&apos;s RERA designated account. Empire never asks for
              payment into a personal account.
            </p>
          </Section>

          {project.faqs.some((f) => f.is_visible) ? (
            <Section id="faqs" title="FAQs">
              <Faqs items={project.faqs} />
            </Section>
          ) : null}

          <section
            id="visit"
            className="scroll-mt-24 rounded-card border border-gold-line bg-noir-800 p-5"
          >
            <LeadPanel
              intent="visit"
              title="Book a site visit"
              intro="Pick a day and a time of day. We confirm the exact time by phone."
              submitLabel="Request a site visit"
              path={path}
              projectSlug={project.slug}
            />
          </section>

          {project.brochure_gated ? (
            <section
              id="brochure"
              className="scroll-mt-24 rounded-card border border-gold-line bg-noir-800 p-5"
            >
              <LeadPanel
                intent="brochure"
                title="Get the brochure"
                intro="Share your number and the brochure opens here. Our team may call you about it."
                submitLabel="Show the brochure"
                path={path}
                projectSlug={project.slug}
              />
            </section>
          ) : null}

          <p className="text-caption text-muted">
            Specifications, plans and the completion date are as declared to{" "}
            {project.rera.authority} and can change only as the law allows. This page is not an
            offer and makes no promise of returns.
          </p>
        </div>

        <aside
          aria-label={`Talk to us about ${project.name}`}
          className="lg:sticky lg:top-32 lg:self-start"
        >
          <div className="flex flex-col gap-4 rounded-card border border-gold-line-strong bg-noir-800 p-5">
            <LeadPanel
              intent="enquiry"
              title="Talk to our sales team"
              intro={`About ${project.name}. We call you back.`}
              submitLabel="Request a call back"
              path={path}
              projectSlug={project.slug}
            />
            <a
              href="#visit"
              className="inline-flex min-h-11 items-center justify-center rounded-pill border border-gold-500 px-5 font-semibold text-gold-300"
            >
              Book a site visit
            </a>
            {brochureHref ? (
              <a
                href={brochureHref}
                className="inline-flex min-h-11 items-center justify-center font-semibold"
              >
                {project.brochure_gated ? "Get the brochure" : "Download brochure (PDF)"}
              </a>
            ) : null}
          </div>
        </aside>
      </div>
    </article>
  );
}

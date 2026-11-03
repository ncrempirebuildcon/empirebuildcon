/**
 * Page-builder blocks on the public site (task 5.5a, D-045). The API sends every block already
 * resolved (5.1, D-038): media with honest labels, the projects of a grid, the picked FAQs, the
 * live offer. A hidden block, or one whose references are gone, never arrives, so nothing here
 * invents a stand-in.
 *
 * COMPLIANCE / honesty:
 *   - Formatted text goes through `FormattedText` only (our parser, never HTML).
 *   - Every number in a `stats` block shows its source and as-of date (D-035).
 *   - Images carry their honest labels (D-033) through `PublicImage`.
 *   - Offers have no countdown and show their terms line and link.
 *   - Videos from YouTube or Vimeo are a link, not an embed: no third-party request or script
 *     before the consent banner (Phase 6; PLAN standing rules).
 * SECURITY: links come as the API validated them (a site path or https); `rel` is set on
 * external ones.
 */
import Link from "next/link";
import type { ReactNode } from "react";
import { FormattedText } from "@empire/ui";
import { PublicImage } from "@/components/media/PublicImage";
import { ProjectCard, PropertyCard } from "@/components/catalogue/Cards";
import { Faqs } from "@/components/catalogue/ProjectSections";
import ProjectMap from "@/components/catalogue/ProjectMap";
import { LeadPanel } from "@/components/leads/LeadPanel";
import { formatCalendarDate } from "@/lib/dates";
import type { components } from "@empire/api-client";

type PublicBlock = components["schemas"]["PublicBlock"];
type Media = components["schemas"]["PublicMedia"];
type Faq = components["schemas"]["PublicFaq"];
type ProjectSummary = components["schemas"]["PublicProjectSummary"];
type PropertySummary = components["schemas"]["PublicPropertySummary"];
type Testimonial = components["schemas"]["PublicTestimonial"];
type Offer = components["schemas"]["PublicOffer"];

/* eslint-disable @typescript-eslint/no-explicit-any -- block data is typed per type below */
type Data = Record<string, any>;

/** True for a site path or an https address (what the API allows for block links). */
export function isSafeHref(href: unknown): href is string {
  return (
    typeof href === "string" &&
    ((href.startsWith("/") && !href.startsWith("//")) || href.startsWith("https://"))
  );
}

function external(href: string): boolean {
  return href.startsWith("https://");
}

function ButtonLink({
  href,
  children,
  secondary = false,
}: {
  href: unknown;
  children: ReactNode;
  secondary?: boolean;
}) {
  if (!isSafeHref(href)) return null;
  const className = secondary
    ? "inline-flex min-h-11 items-center justify-center rounded-pill border border-gold-500 px-5 font-semibold text-gold-300"
    : "inline-flex min-h-11 items-center justify-center rounded-pill bg-gold-500 px-5 font-extrabold text-noir-900 hover:bg-gold-400 hover:text-noir-900";
  return external(href) ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  ) : (
    <Link href={href} className={className}>
      {children}
    </Link>
  );
}

function BlockHeading({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="font-display text-h2-mobile font-semibold sm:text-h2">
      {children}
    </h2>
  );
}

function Img({ media, sizes, className }: { media: Media; sizes?: string; className?: string }) {
  return (
    <PublicImage
      src={media.url}
      alt={media.alt_text || ""}
      label={media.label}
      labelMonth={media.label_month}
      isSample={media.is_sample}
      width={media.width ?? 1200}
      height={media.height ?? 800}
      sizes={sizes ?? "(max-width: 1024px) 100vw, 66vw"}
      containerClassName="block w-full overflow-hidden rounded-tile"
      className={className ?? "h-auto w-full object-cover"}
    />
  );
}

/** "As of 30 Sep 2026 · Source: …" for a stats item (COMPLIANCE, D-035). */
export function statSourceLine(item: { source?: string; as_of?: string }): string {
  const parts: string[] = [];
  if (item.as_of) parts.push(`As of ${formatCalendarDate(item.as_of)}`);
  if (item.source) parts.push(`Source: ${item.source}`);
  return parts.join(" · ");
}

/** The address a YouTube or Vimeo video id opens (never an embed). */
export function videoWatchUrl(provider: unknown, id: unknown): string | null {
  if (typeof id !== "string" || !/^[A-Za-z0-9_-]{5,20}$/.test(id)) return null;
  if (provider === "youtube") return `https://www.youtube.com/watch?v=${id}`;
  if (provider === "vimeo") return `https://vimeo.com/${id}`;
  return null;
}

function Hero({ d, first }: { d: Data; first: boolean }) {
  const Heading = first ? "h1" : "h2";
  return (
    <section className="grid grid-cols-1 items-center gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        {d.eyebrow ? (
          <p className="font-display text-eyebrow tracking-[0.28em] text-gold-400 uppercase">
            {d.eyebrow}
          </p>
        ) : null}
        <Heading
          className={
            first
              ? "font-display text-[clamp(34px,6vw,64px)] leading-tight font-semibold text-balance text-metallic"
              : "font-display text-h2-mobile font-semibold sm:text-h2"
          }
        >
          {d.heading}
        </Heading>
        {d.subheading ? <p className="text-lede text-body">{d.subheading}</p> : null}
        <div className="flex flex-wrap gap-3">
          {d.cta ? <ButtonLink href={d.cta.href}>{d.cta.label}</ButtonLink> : null}
          {d.secondary_cta ? (
            <ButtonLink href={d.secondary_cta.href} secondary>
              {d.secondary_cta.label}
            </ButtonLink>
          ) : null}
        </div>
      </div>
      {d.image ? (
        <PublicImage
          src={d.image.url}
          alt={d.image.alt_text || ""}
          label={d.image.label}
          labelMonth={d.image.label_month}
          isSample={d.image.is_sample}
          width={d.image.width ?? 1600}
          height={d.image.height ?? 1000}
          sizes="(max-width: 1024px) 100vw, 50vw"
          priority={first}
          containerClassName="block w-full overflow-hidden rounded-t-[999px] rounded-b-[18px]"
          className="aspect-[4/3] w-full object-cover"
        />
      ) : null}
    </section>
  );
}

function Stats({ d }: { d: Data }) {
  const items = (d.items ?? []) as {
    value: string;
    label: string;
    source: string;
    as_of: string;
  }[];
  return (
    <section className="flex flex-col gap-5">
      {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
      <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {items.map((item, i) => (
          <div
            key={i}
            className="flex flex-col gap-1 rounded-tile border border-line bg-noir-800 p-4"
          >
            <dt className="order-2 text-small text-body">{item.label}</dt>
            <dd className="order-1 font-display text-3xl font-semibold text-gold-300 tabular-nums">
              {item.value}
            </dd>
            <dd className="order-3 text-caption text-muted" data-testid="stat-source">
              {statSourceLine(item)}
            </dd>
          </div>
        ))}
      </dl>
      {d.note ? <p className="text-caption text-muted">{d.note}</p> : null}
    </section>
  );
}

function Video({ d }: { d: Data }) {
  const media = d.media as Media | undefined;
  const watch = videoWatchUrl(d.provider, d.video_id);
  if (!media && !watch) return null;
  return (
    <section className="flex flex-col gap-3">
      {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
      {media ? (
        <video
          controls
          preload="none"
          poster={media.thumbnail_url ?? undefined}
          className="aspect-video w-full rounded-tile bg-noir-700"
          aria-label={media.alt_text || d.heading || "Video"}
        >
          <source src={media.url} />
        </video>
      ) : watch ? (
        // WHY a link: an embed would load the video site's scripts before consent (Phase 6).
        <a
          href={watch}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center self-start rounded-pill border border-gold-500 px-5 font-semibold text-gold-300"
          data-testid="video-link"
        >
          Watch {d.heading ? `“${d.heading}”` : "the video"} on{" "}
          {d.provider === "vimeo" ? "Vimeo" : "YouTube"}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : null}
      {d.caption ? <p className="text-caption text-muted">{d.caption}</p> : null}
    </section>
  );
}

function OfferBanner({ offer }: { offer: Offer }) {
  return (
    <section
      className="flex flex-col gap-3 rounded-card border border-gold-line-strong bg-noir-800 p-5 md:flex-row md:items-center"
      aria-label="Offer"
    >
      {offer.image ? (
        <div className="md:w-64">
          <Img media={offer.image} sizes="(max-width: 768px) 100vw, 256px" />
        </div>
      ) : null}
      <div className="flex flex-1 flex-col gap-2">
        <p className="font-display text-eyebrow tracking-[0.28em] text-gold-400 uppercase">Offer</p>
        <h2 className="font-display text-h3 font-semibold">{offer.title}</h2>
        {offer.body ? <p className="text-body">{offer.body}</p> : null}
        {offer.terms || offer.terms_url ? (
          <p className="text-caption text-muted">
            {offer.terms}
            {offer.terms_url && isSafeHref(offer.terms_url) ? (
              <>
                {" "}
                <a href={offer.terms_url} className="underline underline-offset-2">
                  Terms and conditions
                </a>
              </>
            ) : null}
          </p>
        ) : null}
        {offer.cta_label && offer.cta_url ? (
          <div>
            <ButtonLink href={offer.cta_url}>{offer.cta_label}</ButtonLink>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function Testimonials({ d }: { d: Data }) {
  const items = (d.testimonials ?? d.items ?? []) as Testimonial[];
  if (items.length === 0) return null;
  return (
    <section className="flex flex-col gap-5">
      {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
      <ul className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {items.map((t) => (
          <li key={t.id}>
            <figure className="flex h-full flex-col gap-3 rounded-card border border-line bg-noir-800 p-5">
              <blockquote className="text-body">“{t.quote}”</blockquote>
              <figcaption className="text-small">
                <span className="font-semibold text-ivory">{t.person_name}</span>
                {t.person_detail ? <span className="text-muted"> · {t.person_detail}</span> : null}
              </figcaption>
            </figure>
          </li>
        ))}
      </ul>
    </section>
  );
}

const LEAD_INTENT: Record<string, "enquiry" | "visit" | "brochure"> = {
  site_visit: "visit",
  brochure: "brochure",
};

/** One block. `first` makes a leading hero the page's h1. */
export function BlockView({
  block,
  first,
  path,
}: {
  block: PublicBlock;
  first: boolean;
  path: string;
}) {
  const d = (block.data ?? {}) as Data;
  switch (block.type) {
    case "hero":
      return <Hero d={d} first={first} />;
    case "rich_text":
      return (
        <section className="flex max-w-[42em] flex-col gap-3">
          {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
          <FormattedText text={String(d.body ?? "")} />
        </section>
      );
    case "image":
      return d.image ? (
        <figure className="flex flex-col gap-2">
          <Img media={d.image} />
          {d.caption ? (
            <figcaption className="text-caption text-muted">{d.caption}</figcaption>
          ) : null}
        </figure>
      ) : null;
    case "gallery": {
      const images = (d.images ?? []) as Media[];
      return images.length ? (
        <section className="flex flex-col gap-4">
          {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {images.map((m) => (
              <li key={m.id}>
                <Img
                  media={m}
                  sizes="(max-width: 640px) 100vw, 33vw"
                  className="aspect-[4/3] w-full object-cover"
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null;
    }
    case "video":
      return <Video d={d} />;
    case "project_grid": {
      const projects = (d.projects ?? []) as ProjectSummary[];
      return projects.length ? (
        <section className="flex flex-col gap-5">
          {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
          <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <li key={p.id} className="flex">
                <ProjectCard project={p} />
              </li>
            ))}
          </ul>
        </section>
      ) : null;
    }
    case "property_grid": {
      const properties = (d.properties ?? []) as PropertySummary[];
      return properties.length ? (
        <section className="flex flex-col gap-5">
          {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
          <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {properties.map((p) => (
              <li key={p.id} className="flex">
                <PropertyCard property={p} />
              </li>
            ))}
          </ul>
        </section>
      ) : null;
    }
    case "cta":
      return (
        <section className="flex flex-col items-start gap-3 rounded-card border border-gold-line bg-noir-800 p-6">
          {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
          {d.text ? <p className="max-w-[42em] text-body">{d.text}</p> : null}
          <ButtonLink href={d.href}>{d.label}</ButtonLink>
        </section>
      );
    case "lead_form":
      return (
        <section className="rounded-card border border-gold-line-strong bg-noir-800 p-5 lg:max-w-2xl">
          <LeadPanel
            intent={LEAD_INTENT[d.source] ?? "enquiry"}
            title={d.heading || (d.source === "site_visit" ? "Book a site visit" : "Talk to us")}
            intro={d.intro ?? undefined}
            submitLabel={d.source === "site_visit" ? "Request a site visit" : "Send"}
            path={path}
            projectSlug={d.project_slug ?? null}
            source={d.source}
          />
        </section>
      );
    case "faq_list": {
      const faqs = (d.faqs ?? d.items ?? []) as Faq[];
      return faqs.length ? (
        <section className="flex flex-col gap-4">
          {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
          <Faqs items={faqs} />
        </section>
      ) : null;
    }
    case "stats":
      return <Stats d={d} />;
    case "testimonials":
      return <Testimonials d={d} />;
    case "offer_banner":
      return d.offer ? <OfferBanner offer={d.offer as Offer} /> : null;
    case "map": {
      const p = d.project as
        | {
            name: string;
            slug: string;
            lat: number | null;
            lng: number | null;
            address: string;
            directions_url: string | null;
          }
        | undefined;
      if (!p) return null;
      return (
        <section className="flex flex-col gap-3">
          <BlockHeading>{d.heading || p.name}</BlockHeading>
          {p.address ? <p className="text-body">{p.address}</p> : null}
          {p.directions_url ? (
            <a
              href={p.directions_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center self-start font-semibold"
            >
              Get directions<span className="sr-only"> (opens Google Maps in a new tab)</span>
            </a>
          ) : null}
          {p.lat != null && p.lng != null && p.directions_url ? (
            <ProjectMap
              lat={p.lat}
              lng={p.lng}
              name={p.name}
              address={p.address || null}
              reraNumber={null}
              directionsUrl={p.directions_url}
            />
          ) : null}
        </section>
      );
    }
    case "steps": {
      const items = (d.items ?? []) as { title: string; text?: string | null }[];
      return (
        <section className="flex flex-col gap-4">
          {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
          <ol className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            {items.map((s, i) => (
              <li
                key={i}
                className="flex flex-col gap-2 rounded-tile border border-line bg-noir-800 p-4"
              >
                <span className="font-display text-2xl text-gold-400" aria-hidden="true">
                  {i + 1}
                </span>
                <h3 className="font-semibold text-ivory">{s.title}</h3>
                {s.text ? <p className="text-small text-body">{s.text}</p> : null}
              </li>
            ))}
          </ol>
        </section>
      );
    }
    case "columns": {
      const cols = (d.columns ?? []) as { heading?: string | null; body: string }[];
      return (
        <section className="flex flex-col gap-4">
          {d.heading ? <BlockHeading>{d.heading}</BlockHeading> : null}
          <div
            className={`grid grid-cols-1 gap-6 ${cols.length === 3 ? "md:grid-cols-3" : "md:grid-cols-2"}`}
          >
            {cols.map((c, i) => (
              <div key={i} className="flex flex-col gap-2">
                {c.heading ? <h3 className="font-semibold text-ivory">{c.heading}</h3> : null}
                <FormattedText text={c.body} />
              </div>
            ))}
          </div>
        </section>
      );
    }
    case "divider":
      return (
        <div className="star-rule text-xs" aria-hidden="true">
          ✦
        </div>
      );
    default:
      // A type this site doesn't know yet is left out rather than shown wrongly.
      return null;
  }
}

/** The page's blocks in order. A leading hero becomes the page's only h1. */
export function BlockList({ blocks, path }: { blocks: PublicBlock[]; path: string }) {
  const ordered = [...blocks]
    .filter((b) => b.is_visible !== false)
    .sort((a, b) => a.sort_order - b.sort_order);
  return (
    <div className="flex flex-col gap-14">
      {ordered.map((b, i) => (
        <BlockView key={b.id} block={b} first={i === 0 && b.type === "hero"} path={path} />
      ))}
    </div>
  );
}

/** True when the page's first block is a hero (it then carries the page's h1). */
export function startsWithHero(blocks: PublicBlock[]): boolean {
  const first = [...blocks]
    .filter((b) => b.is_visible !== false)
    .sort((a, b) => a.sort_order - b.sort_order)[0];
  return first?.type === "hero";
}

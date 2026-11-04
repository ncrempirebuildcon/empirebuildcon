/**
 * Metadata, share images and structured data for the public site (task 5.6, D-047).
 *
 * Implements ARCHITECTURE §16 (SEO):
 *   - Every public page's `<title>`, description, canonical URL on SITE_URL (production:
 *     https://empirebuildcon.com), Open Graph and Twitter card, through `pageMetadata`.
 *   - JSON-LD (schema.org) builders: Organization, RealEstateListing (projects and homes),
 *     FAQPage and BreadcrumbList. `JsonLd` (components/JsonLd.tsx) writes them with the CSP nonce.
 *
 * COMPLIANCE (AGENTS.md "Honest content"):
 *   - Structured data says only what the page says: no price when the page shows "price on
 *     request", carpet area labelled as carpet area, the UP-RERA number as the listing's
 *     identifier, nothing in `[brackets]` (placeholders) and nothing for sample data.
 *   - No ratings or review counts: testimonials are not reviews (D-035).
 *
 * Indexing stays off until go-live (root layout, Phase 9 gate); a page's own `noindex` (landing
 * pages, the CMS's SEO tab) is kept after that too.
 */
import type { Metadata } from "next";
import type { components } from "@empire/api-client";
import { isPlaceholder } from "./format";

type Media = components["schemas"]["PublicMedia"];
type Seo = components["schemas"]["PublicSeo"];
type Area = components["schemas"]["Area"];
type Price = components["schemas"]["Price"];
type Rera = components["schemas"]["PublicRera"];
type Faq = components["schemas"]["PublicFaq"];

export const SHARE_IMAGE = { width: 1200, height: 630 } as const;

/**
 * The last fallback, so no page is without a description (task 5.7: Lighthouse SEO). It says
 * only what the site itself shows (the projects list's heading and the RERA rule).
 */
export const SITE_DESCRIPTION =
  "Empire — Delivering Happiness. Projects and homes in Uttar Pradesh, each with its UP-RERA registration.";

/** The logo on black (public/brand/share-default.png), for pages with no image of their own. */
const DEFAULT_SHARE_IMAGE = () => ({
  url: absoluteUrl("/brand/share-default.png"),
  ...SHARE_IMAGE,
  alt: "Empire — Delivering Happiness",
});
const DESCRIPTION_MAX = 160;
const SQFT_PER_SQM = 10.7639;
const CLOUDINARY_UPLOAD = "/image/upload/";

/** The canonical origin, without a trailing slash. */
export function siteOrigin(): string {
  return (process.env.SITE_URL ?? "http://localhost:3000").replace(/\/+$/, "");
}

/** An absolute URL on the canonical origin for a site path ("/projects/x"). */
export function absoluteUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${siteOrigin()}${path.startsWith("/") ? path : `/${path}`}`;
}

/** A value fit for public metadata: not empty and not a `[placeholder]`. */
function real(value: string | null | undefined): string | null {
  if (!value || !value.trim() || isPlaceholder(value)) return null;
  return value.trim();
}

/**
 * Plain text for a meta description: formatting marks removed, whitespace collapsed, cut at a
 * word before 160 characters with "…".
 */
export function plainExcerpt(
  text: string | null | undefined,
  max = DESCRIPTION_MAX,
): string | null {
  const value = real(text);
  if (!value) return null;
  const plain = value
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1") // [label](url) → label
    .replace(/[*_`#>]+/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!plain) return null;
  if (plain.length <= max) return plain;
  const cut = plain.slice(0, max - 1);
  const space = cut.lastIndexOf(" ");
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[\s,.;:–-]+$/, "")}…`;
}

/**
 * A 1200×630 share image. Cloudinary images are cropped there (`c_fill,g_auto`); any other
 * image (the development store) is used as it is.
 */
export function shareImage(media: Media | null | undefined): {
  url: string;
  width?: number;
  height?: number;
  alt: string;
} | null {
  if (!media || media.kind !== "image" || !media.url) return null;
  const alt = real(media.alt_text) ?? "";
  const at = media.url.indexOf(CLOUDINARY_UPLOAD);
  if (media.url.startsWith("https://res.cloudinary.com/") && at !== -1) {
    const head = media.url.slice(0, at + CLOUDINARY_UPLOAD.length);
    const rest = media.url.slice(at + CLOUDINARY_UPLOAD.length);
    const first = rest.split("/")[0] ?? "";
    // An existing transformation ("c_limit,w_800") is replaced; the version and id are kept.
    const isTransform = first !== "" && first.split(",").every((p) => /^[a-z]{1,3}_[^,]+$/.test(p));
    const tail = isTransform ? rest.slice(first.length + 1) : rest;
    const transform = `c_fill,g_auto,w_${SHARE_IMAGE.width},h_${SHARE_IMAGE.height},f_jpg,q_auto`;
    return { url: `${head}${transform}/${tail}`, ...SHARE_IMAGE, alt };
  }
  return { url: absoluteUrl(media.url), alt };
}

export interface PageMeta {
  /** The page's own title; the site's title template adds the suffix. */
  title: string;
  /** The canonical site path ("/projects/x"). The CMS's canonical path wins when set. */
  path: string;
  seo?: Seo | null;
  /** Used when the CMS gave no description (first choice first). */
  fallbackDescriptions?: (string | null | undefined)[];
  image?: Media | null;
  noindex?: boolean;
  type?: "website" | "article";
  siteName?: string;
}

/** Next.js metadata for one public page (title, description, canonical, share cards). */
export function pageMetadata(meta: PageMeta): Metadata {
  const title = real(meta.seo?.title) ?? meta.title;
  const description =
    plainExcerpt(meta.seo?.description) ??
    (meta.fallbackDescriptions ?? []).map((d) => plainExcerpt(d)).find(Boolean) ??
    SITE_DESCRIPTION;
  // SECURITY: only a site path from the CMS becomes the canonical; never another host.
  const cmsCanonical = meta.seo?.canonical_path;
  const canonicalPath =
    cmsCanonical && cmsCanonical.startsWith("/") && !cmsCanonical.startsWith("//")
      ? cmsCanonical
      : meta.path;
  const url = absoluteUrl(canonicalPath);
  const image = shareImage(meta.seo?.og_image) ?? shareImage(meta.image) ?? DEFAULT_SHARE_IMAGE();
  const images = [image];
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      type: meta.type ?? "website",
      url,
      title,
      description,
      siteName: meta.siteName ?? "Empire",
      locale: "en_IN",
      images,
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [image.url],
    },
    ...(meta.noindex || meta.seo?.noindex ? { robots: { index: false, follow: false } } : {}),
  };
}

// --- Structured data (JSON-LD) --------------------------------------------------------------

type Ld = Record<string, unknown>;

/** JSON for a `<script type="application/ld+json">`: `<` escaped, so no text can close it. */
export function ldJson(data: Ld | Ld[]): string {
  return JSON.stringify(data)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

function compact<T extends Ld>(obj: T): T {
  return Object.fromEntries(
    Object.entries(obj).filter(
      ([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0),
    ),
  ) as T;
}

export function breadcrumbLd(items: { href?: string; label: string }[]): Ld | null {
  if (items.length < 2) return null;
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) =>
      compact({
        "@type": "ListItem",
        position: i + 1,
        name: item.label,
        item: item.href ? absoluteUrl(item.href) : undefined,
      }),
    ),
  };
}

type Company = components["schemas"]["PublicCompany"];

export function organizationLd(company: Company, social: Record<string, string> = {}): Ld {
  return compact({
    "@context": "https://schema.org",
    "@type": "Organization",
    name: real(company.name) ?? "Empire",
    legalName: real(company.legal_name) ?? undefined,
    slogan: real(company.tagline) ?? undefined,
    url: absoluteUrl("/"),
    logo: absoluteUrl("/brand/logo-stacked-noir.svg"),
    telephone: company.phones.map(real).find(Boolean) ?? undefined,
    email: company.emails.map(real).find(Boolean) ?? undefined,
    address: real(company.address) ?? undefined,
    sameAs: Object.values(social).filter((u) => u.startsWith("https://") && !isPlaceholder(u)),
  });
}

function postalAddress(location: {
  address_line?: string | null;
  city?: { name: string } | null;
  state?: string | null;
  pincode?: string | null;
}): Ld {
  return compact({
    "@type": "PostalAddress",
    streetAddress: real(location.address_line) ?? undefined,
    addressLocality: real(location.city?.name) ?? undefined,
    addressRegion: real(location.state) ?? undefined,
    postalCode: real(location.pincode) ?? undefined,
    addressCountry: "IN",
  });
}

/**
 * An Offer for the listing, or nothing when the page shows no number (price on request).
 * COMPLIANCE: like the page's note, it says the price excludes GST (and, in its description,
 * stamp duty and registration).
 */
function offers(price: Price, onRequest = false): Ld | null {
  if (onRequest || price.on_request || price.min_inr == null) return null;
  const low = price.min_inr;
  const high = price.max_inr ?? low;
  const terms = {
    priceSpecification: {
      "@type": "PriceSpecification",
      priceCurrency: "INR",
      valueAddedTaxIncluded: false,
    },
    description: "Price excludes GST, stamp duty and registration.",
  };
  return low === high
    ? { "@type": "Offer", priceCurrency: "INR", price: low, ...terms }
    : { "@type": "AggregateOffer", priceCurrency: "INR", lowPrice: low, highPrice: high, ...terms };
}

/**
 * Carpet area in sq ft, only when the area is a carpet area (the site never relabels areas); a
 * range stays a range, as the page shows it.
 */
function carpetArea(area: Area | null | undefined): Ld | null {
  if (!area || area.basis !== "carpet" || area.min_sqm == null) return null;
  const min = Math.round(area.min_sqm * SQFT_PER_SQM);
  const max = area.max_sqm != null ? Math.round(area.max_sqm * SQFT_PER_SQM) : min;
  return {
    "@type": "QuantitativeValue",
    ...(max > min ? { minValue: min, maxValue: max } : { value: min }),
    unitCode: "FTK",
    unitText: "sq ft (carpet area)",
  };
}

function reraId(rera: Rera | null | undefined): Ld | null {
  const number = real(rera?.number);
  if (!number) return null;
  return { "@type": "PropertyValue", propertyID: rera?.authority || "UP-RERA", value: number };
}

type ProjectDetail = components["schemas"]["PublicProjectDetail"];

export function projectLd(project: ProjectDetail, path: string): Ld | null {
  if (project.is_sample) return null; // COMPLIANCE: sample data is never offered to search engines
  const { lat, lng } = project.location;
  return compact({
    "@context": "https://schema.org",
    "@type": "RealEstateListing",
    name: project.name,
    url: absoluteUrl(path),
    description: plainExcerpt(project.tagline) ?? plainExcerpt(project.description) ?? undefined,
    image: shareImage(project.cover)?.url,
    identifier: reraId(project.rera),
    offers: offers(project.price),
    about: compact({
      "@type": "ApartmentComplex",
      name: project.name,
      address: postalAddress(project.location),
      geo:
        lat != null && lng != null
          ? { "@type": "GeoCoordinates", latitude: lat, longitude: lng }
          : undefined,
      numberOfAccommodationUnits: project.total_units ?? undefined,
    }),
  });
}

type PropertyDetail = components["schemas"]["PublicPropertyDetail"];

const RESIDENCE_TYPE: Record<string, string> = {
  apartment: "Apartment",
  penthouse: "Apartment",
  villa: "SingleFamilyResidence",
  plot: "Place",
};

export function propertyLd(
  property: PropertyDetail,
  project: ProjectDetail,
  path: string,
  name: string,
): Ld | null {
  if (property.is_sample || project.is_sample) return null;
  return compact({
    "@context": "https://schema.org",
    "@type": "RealEstateListing",
    name: `${name} · ${project.name}`,
    url: absoluteUrl(path),
    identifier: reraId(project.rera),
    offers: offers(property.price, project.price.on_request),
    about: compact({
      "@type": RESIDENCE_TYPE[property.property_type] ?? "Accommodation",
      name,
      numberOfRooms: property.bhk ?? undefined,
      numberOfBathroomsTotal: property.bathrooms ?? undefined,
      floorSize: carpetArea(property.area),
      address: postalAddress(project.location),
      containedInPlace: { "@type": "ApartmentComplex", name: project.name },
    }),
  });
}

export function faqLd(faqs: Faq[]): Ld | null {
  const shown = faqs.filter((f) => f.is_visible !== false && real(f.question) && real(f.answer));
  if (shown.length === 0) return null;
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: shown.map((f) => ({
      "@type": "Question",
      name: f.question,
      acceptedAnswer: { "@type": "Answer", text: plainExcerpt(f.answer, 1000) },
    })),
  };
}

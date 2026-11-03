import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  absoluteUrl,
  breadcrumbLd,
  faqLd,
  ldJson,
  organizationLd,
  pageMetadata,
  plainExcerpt,
  projectLd,
  propertyLd,
  shareImage,
} from "../src/lib/public/seo";

const media = {
  id: "m1",
  kind: "image",
  url: "https://res.cloudinary.com/empire/image/upload/c_limit,w_800/v17/projects/tower.jpg",
  alt_text: "Tower A at dusk",
  label: "artist_impression",
  label_month: null,
  is_sample: false,
  width: 800,
  height: 600,
  thumbnail_url: null,
  format: "jpg",
  duration_s: null,
};
const rera = { authority: "UP-RERA", number: "UPRERAPRJ123456", qr: null, url: null };
const location = {
  address_line: "Sector 7",
  city: { name: "Lucknow", slug: "lucknow" },
  locality: null,
  state: "Uttar Pradesh",
  pincode: "226010",
  lat: 26.85,
  lng: 80.95,
  google_maps_url: null,
};
const project: Record<string, unknown> = {
  name: "Empire Heights",
  slug: "empire-heights",
  tagline: "Garden homes",
  description: null,
  is_sample: false,
  cover: media,
  rera,
  location,
  total_units: 120,
  price: { on_request: false, min_inr: 6500000, max_inr: 9000000 },
  faqs: [],
};

let saved: string | undefined;
beforeEach(() => {
  saved = process.env.SITE_URL;
  process.env.SITE_URL = "https://empirebuildcon.com/";
});
afterEach(() => {
  process.env.SITE_URL = saved;
});

describe("metadata", () => {
  it("makes canonical URLs on the .com origin", () => {
    expect(absoluteUrl("/projects/x")).toBe("https://empirebuildcon.com/projects/x");
    const meta = pageMetadata({ title: "Empire Heights", path: "/projects/empire-heights" });
    expect(meta.alternates?.canonical).toBe("https://empirebuildcon.com/projects/empire-heights");
  });

  it("uses the CMS's SEO fields first, and never another host as canonical", () => {
    const meta = pageMetadata({
      title: "Page",
      path: "/about",
      seo: {
        title: "About Empire",
        description: "Who we are.",
        canonical_path: "//evil.example/x",
        noindex: true,
        og_image: null,
      },
    });
    expect(meta.title).toBe("About Empire");
    expect(meta.description).toBe("Who we are.");
    expect(meta.alternates?.canonical).toBe("https://empirebuildcon.com/about");
    expect(meta.robots).toEqual({ index: false, follow: false });
  });

  it("falls back to plain text descriptions, never placeholders", () => {
    const meta = pageMetadata({
      title: "X",
      path: "/x",
      fallbackDescriptions: ["[Tagline]", "We *build* homes.\n\n- Honest"],
    });
    expect(meta.description).toBe("We build homes. Honest");
    expect(plainExcerpt("word ".repeat(60))?.length).toBeLessThanOrEqual(160);
    expect(plainExcerpt("word ".repeat(60))?.endsWith("…")).toBe(true);
  });

  it("crops Cloudinary share images to 1200×630 and keeps the version and id", () => {
    expect(shareImage(media)?.url).toBe(
      "https://res.cloudinary.com/empire/image/upload/c_fill,g_auto,w_1200,h_630,f_jpg,q_auto/v17/projects/tower.jpg",
    );
    expect(shareImage({ ...media, url: "/media-dev/a.png" })?.url).toBe(
      "https://empirebuildcon.com/media-dev/a.png",
    );
    expect(shareImage({ ...media, kind: "video" })).toBeNull();
    const meta = pageMetadata({ title: "X", path: "/x", image: media });
    expect(meta.twitter).toMatchObject({ card: "summary_large_image" });
    const plain = pageMetadata({ title: "X", path: "/x" });
    expect(JSON.stringify(plain.openGraph)).toContain(
      "https://empirebuildcon.com/brand/share-default.png",
    );
  });
});

describe("structured data", () => {
  it("escapes JSON so nothing can close the script tag", () => {
    expect(ldJson({ name: "</script><script>alert(1)</script>" })).not.toContain("<");
  });

  it("lists a project with its RERA number, address and price range", () => {
    const ld = projectLd(project as never, "/projects/empire-heights") as Record<string, unknown>;
    expect(ld["@type"]).toBe("RealEstateListing");
    expect(ld.identifier).toEqual({
      "@type": "PropertyValue",
      propertyID: "UP-RERA",
      value: "UPRERAPRJ123456",
    });
    expect(ld.offers).toEqual({
      "@type": "AggregateOffer",
      priceCurrency: "INR",
      lowPrice: 6500000,
      highPrice: 9000000,
    });
    expect(JSON.stringify(ld)).toContain("Lucknow");
  });

  it("gives no price when the page shows price on request, and nothing for sample data", () => {
    const onRequest = projectLd(
      { ...project, price: { on_request: true, min_inr: 1, max_inr: 2 } } as never,
      "/p",
    ) as Record<string, unknown>;
    expect(onRequest.offers).toBeUndefined();
    expect(projectLd({ ...project, is_sample: true } as never, "/p")).toBeNull();
  });

  it("labels a home's floor size as carpet area and honours project price on request", () => {
    const property = {
      is_sample: false,
      property_type: "apartment",
      bhk: 2,
      bathrooms: 2,
      area: { basis: "carpet", display_unit: "sqft", min_sqm: 100 },
      price: { on_request: false, min_inr: 7000000, max_inr: null },
    };
    const ld = propertyLd(property as never, project as never, "/projects/x/2-bhk", "2 BHK") as {
      about: { floorSize: unknown };
      offers?: unknown;
    };
    expect(ld.about.floorSize).toMatchObject({ value: 1076, unitText: "sq ft (carpet area)" });
    expect(ld.offers).toEqual({ "@type": "Offer", priceCurrency: "INR", price: 7000000 });
    const hidden = propertyLd(
      property as never,
      { ...project, price: { on_request: true } } as never,
      "/x",
      "2 BHK",
    ) as { offers?: unknown };
    expect(hidden.offers).toBeUndefined();
    const superArea = propertyLd(
      { ...property, area: { basis: "super_builtup", min_sqm: 100 } } as never,
      project as never,
      "/x",
      "2 BHK",
    ) as { about: { floorSize?: unknown } };
    expect(superArea.about.floorSize).toBeUndefined();
  });

  it("builds breadcrumbs, FAQs and the organisation without placeholders", () => {
    const crumbs = breadcrumbLd([{ href: "/", label: "Home" }, { label: "Projects" }]) as {
      itemListElement: Record<string, unknown>[];
    };
    expect(crumbs.itemListElement[0]).toMatchObject({
      position: 1,
      item: "https://empirebuildcon.com/",
    });
    expect(crumbs.itemListElement[1]?.item).toBeUndefined();
    expect(breadcrumbLd([{ label: "Only" }])).toBeNull();
    const faqs = faqLd([
      {
        id: "f",
        question: "Is it RERA registered?",
        answer: "Yes.",
        sort_order: 0,
        is_visible: true,
      } as never,
    ]);
    expect(JSON.stringify(faqs)).toContain("Is it RERA registered?");
    expect(faqLd([])).toBeNull();
    const org = organizationLd(
      { name: "Empire", phones: ["[Phone]"], emails: [], address: null, tagline: null } as never,
      { instagram: "https://instagram.com/empire", x: "[handle]" },
    );
    expect(org).not.toHaveProperty("telephone");
    expect(org.sameAs).toEqual(["https://instagram.com/empire"]);
  });
});

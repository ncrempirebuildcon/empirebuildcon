import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { components } from "@empire/api-client";
import {
  bhkLabel,
  cityPath,
  directionsUrl,
  distanceLabel,
  filterHref,
  formatMonthYear,
  pageWindow,
  parseFilters,
  projectQuery,
  propertyPath,
  propertyQuery,
  PROPERTY_SORTS,
} from "../src/lib/public/catalogue";
import { PRICE_NOTE, priceNote, priceText, PriceText } from "../src/components/catalogue/Facts";
import { portalHost, ReraBlock, towerNumbers } from "../src/components/catalogue/ReraBlock";

type Price = components["schemas"]["Price"];
type Rera = components["schemas"]["PublicRera"];
type Tower = components["schemas"]["Tower"];

const price = (p: Partial<Price>): Price => ({ on_request: false, display: "", ...p });

describe("parseFilters", () => {
  it("keeps valid filters and drops anything the API would refuse", () => {
    const f = parseFilters({
      q: "  aurum  ",
      status: "ongoing",
      city: "greater-noida",
      locality: "Bad Slug!",
      type: "villa",
      bhk: "3",
      budget: "75l-1.5cr",
      sort: "price_asc",
      page: "2",
    });
    expect(f).toEqual({
      q: "aurum",
      status: "ongoing",
      city: "greater-noida",
      locality: undefined,
      type: "villa",
      bhk: "3",
      budget: "75l-1.5cr",
      sort: "price_asc",
      page: 2,
    });
  });

  it("falls back to page 1 and no filter on nonsense", () => {
    const f = parseFilters({
      status: "sold",
      bhk: "9",
      budget: "free",
      sort: "random",
      page: "-3",
    });
    expect(f).toEqual({
      q: undefined,
      status: undefined,
      city: undefined,
      locality: undefined,
      type: undefined,
      bhk: undefined,
      budget: undefined,
      sort: undefined,
      page: 1,
    });
    expect(parseFilters({ page: "abc" }).page).toBe(1);
    expect(parseFilters({ page: "5000" }).page).toBe(1);
  });

  it("uses the first value of a repeated parameter and caps the search text", () => {
    const f = parseFilters({ city: ["noida", "lucknow"], q: "x".repeat(500) });
    expect(f.city).toBe("noida");
    expect(f.q).toHaveLength(200);
  });

  it("accepts only the sorts of the page it is given", () => {
    expect(parseFilters({ sort: "size_desc" }).sort).toBeUndefined(); // projects page
    expect(parseFilters({ sort: "size_desc" }, PROPERTY_SORTS).sort).toBe("size_desc");
  });
});

describe("API queries", () => {
  it("turns a budget band into whole-rupee bounds", () => {
    expect(projectQuery(parseFilters({ budget: "under-75l" }))).toMatchObject({
      budget_min: undefined,
      budget_max: 7_500_000,
    });
    expect(projectQuery(parseFilters({ budget: "75l-1.5cr" }))).toMatchObject({
      budget_min: 7_500_000,
      budget_max: 15_000_000,
    });
    expect(projectQuery(parseFilters({ budget: "above-1.5cr" }))).toMatchObject({
      budget_min: 15_000_000,
      budget_max: undefined,
    });
  });

  it("sends BHK as a number and the status as project_status for properties", () => {
    const f = parseFilters({ bhk: "2", status: "completed", q: "ignored" });
    expect(projectQuery(f)).toMatchObject({ bhk: 2, status: "completed", q: "ignored" });
    const q = propertyQuery(f);
    expect(q).toMatchObject({ bhk: 2, project_status: "completed" });
    expect(q).not.toHaveProperty("q");
  });
});

describe("filterHref", () => {
  const base = parseFilters({ city: "noida", bhk: "3", page: "4" });

  it("keeps the other filters and goes back to page 1 when a filter changes", () => {
    expect(filterHref("/projects", base, { bhk: "2" })).toBe("/projects?city=noida&bhk=2");
  });

  it("keeps the filters when only the page changes", () => {
    expect(filterHref("/projects", base, { page: 5 })).toBe("/projects?city=noida&bhk=3&page=5");
    expect(filterHref("/projects", base, { page: 1 })).toBe("/projects?city=noida&bhk=3");
  });

  it("removes a filter set to undefined and encodes values", () => {
    expect(filterHref("/projects", base, { city: undefined })).toBe("/projects?bhk=3");
    const q = parseFilters({ q: "sector 150 & more" });
    expect(filterHref("/projects", q)).toBe("/projects?q=sector+150+%26+more");
  });
});

describe("paths and labels", () => {
  it("builds the public paths (twin of seo/paths.py)", () => {
    expect(propertyPath("aurum-heights", "3-bhk")).toBe("/projects/aurum-heights/3-bhk");
    expect(cityPath("noida")).toBe("/cities/noida");
  });

  it("formats possession by month and BHK labels", () => {
    expect(formatMonthYear("2029-06-30")).toBe("June 2029");
    expect(formatMonthYear("2029-13-01")).toBeNull();
    expect(formatMonthYear(null)).toBeNull();
    expect(bhkLabel(3)).toBe("3 BHK");
    expect(bhkLabel(2.5)).toBe("2.5 BHK");
    expect(bhkLabel(null)).toBeNull();
    expect(bhkLabel(0)).toBeNull();
  });

  it("labels distances and leaves out what isn't set", () => {
    expect(distanceLabel(1.8, null)).toBe("≈ 1.8 km");
    expect(distanceLabel(3, 8)).toBe("≈ 3 km · 8 min");
    expect(distanceLabel(12.4, null)).toBe("≈ 12 km");
    expect(distanceLabel(null, null)).toBeNull();
  });

  it("shows a window of page numbers with gaps", () => {
    expect(pageWindow(1, 3)).toEqual([1, 2, 3]);
    expect(pageWindow(6, 12)).toEqual([1, null, 5, 6, 7, null, 12]);
    expect(pageWindow(1, 12)).toEqual([1, 2, null, 12]);
  });

  it("builds directions from the pin, else the stored link", () => {
    expect(directionsUrl({ directions_url: "https://maps.example/d" })).toBe(
      "https://maps.example/d",
    );
    expect(directionsUrl({ lat: 28.5, lng: 77.4 })).toBe(
      "https://www.google.com/maps/dir/?api=1&destination=28.5,77.4",
    );
    expect(directionsUrl({ google_maps_url: "https://maps.example/p" })).toBe(
      "https://maps.example/p",
    );
    expect(directionsUrl({})).toBeNull();
  });
});

describe("price honesty (COMPLIANCE)", () => {
  it("never shows numbers when the price is on request", () => {
    const p = price({ on_request: true, display: "₹ 78 L – ₹ 1.25 Cr", min_inr: 7_800_000 });
    expect(priceText(p)).toBe("Price on request");
    const html = renderToStaticMarkup(React.createElement(PriceText, { price: p }));
    expect(html).toContain("Price on request");
    expect(html).not.toMatch(/₹|78|1\.25/);
  });

  it("always carries the tax note", () => {
    expect(priceNote(price({}))).toBe(PRICE_NOTE);
    expect(priceNote(price({ note: "Starting base price" }))).toBe(
      `Starting base price (${PRICE_NOTE})`,
    );
    expect(
      priceNote(price({ note: "Base price; excludes GST, stamp duty and registration" })),
    ).toBe("Base price; excludes GST, stamp duty and registration");
    const html = renderToStaticMarkup(
      React.createElement(PriceText, { price: price({ display: "₹ 78 L – ₹ 1.25 Cr" }) }),
    );
    expect(html).toContain("₹ 78 L – ₹ 1.25 Cr");
    expect(html).toContain("stamp duty");
  });
});

describe("ReraBlock (COMPLIANCE)", () => {
  const rera: Rera = {
    authority: "UP-RERA",
    number: "UPRERAPRJ123",
    url: "https://www.up-rera.in",
    qr: { id: "q1", kind: "image", url: "/qr.png", is_sample: false } as Rera["qr"],
  };
  const tower = (t: Partial<Tower>): Tower =>
    ({ id: "t", kind: "tower", name: "A", sort_order: 0, status: "planned", ...t }) as Tower;

  it("shows the number, the QR and the portal link", () => {
    const html = renderToStaticMarkup(
      React.createElement(ReraBlock, { rera, projectName: "Aurum" }),
    );
    expect(html).toContain("UPRERAPRJ123");
    expect(html).toContain("UP-RERA QR code for Aurum");
    expect(html).toContain('href="https://www.up-rera.in"');
    expect(html).toContain("Verify on up-rera.in");
  });

  it("still links the portal when the QR or number is missing", () => {
    const html = renderToStaticMarkup(
      React.createElement(ReraBlock, {
        rera: { authority: "UP-RERA", number: null, url: null, qr: null },
        projectName: "Aurum",
      }),
    );
    expect(html).toContain("Verify on up-rera.in");
    expect(html).toContain('href="https://www.up-rera.in"');
  });

  it("lists tower numbers that differ from the project's, in order", () => {
    const towers = [
      tower({ id: "b", name: "B", sort_order: 2, rera_number: "UPRERAPRJ999" }),
      tower({ id: "a", name: "A", sort_order: 1, rera_number: "UPRERAPRJ123" }),
      tower({ id: "c", name: "C", sort_order: 0, rera_number: "UPRERAPRJ555" }),
    ];
    expect(towerNumbers(rera, towers)).toEqual([
      { name: "C", number: "UPRERAPRJ555" },
      { name: "B", number: "UPRERAPRJ999" },
    ]);
    const html = renderToStaticMarkup(
      React.createElement(ReraBlock, { rera, towers, projectName: "Aurum" }),
    );
    expect(html).toContain("UPRERAPRJ555");
  });

  it("names the portal host from the stored URL", () => {
    expect(portalHost("https://www.up-rera.in/projects")).toBe("up-rera.in");
    expect(portalHost(null)).toBe("up-rera.in");
    expect(portalHost("not a url")).toBe("up-rera.in");
  });
});

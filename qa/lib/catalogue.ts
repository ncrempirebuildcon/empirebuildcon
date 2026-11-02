/**
 * Seeds published projects for the public catalogue journeys (task 5.3), through the CMS API
 * as the signed-in super-admin (no extra sign-ins).
 *
 * Every project is named "E2E Catalogue …" with a fresh run id, so it can't pass for a real
 * project and parallel runs don't collide. It lives in the sample city from the sample seed
 * (`empire-api seed --sample`, global-setup.ts).
 */
import { expect, type Page } from "@playwright/test";
import { apiCall, apiUpload, runId } from "./auth";
import { samplePhoto, sampleQr } from "./files";

export interface CatalogueProject {
  id: string;
  slug: string;
  name: string;
  rera: string;
  configSlugs: string[];
}

async function sampleCityId(page: Page): Promise<string> {
  const res = await apiCall(page, "GET", "/api/v1/admin/cities?per_page=100");
  expect(res.status()).toBe(200);
  const { items } = (await res.json()) as { items: { id: string; slug: string }[] };
  const city = items.find((c) => c.slug === "sample-city");
  if (!city) throw new Error("the sample seed creates sample-city (global-setup.ts)");
  return city.id;
}

/**
 * A published project with a city, a pin, a tagline and description, two configurations with
 * carpet area and prices, a labelled cover photo, a FAQ-free page and the RERA QR.
 */
export async function catalogueProject(
  page: Page,
  options: { priceOnRequest?: boolean; publish?: boolean } = {},
): Promise<CatalogueProject> {
  const id = runId();
  const name = `E2E Catalogue ${id}`;
  const rera = `UPRERAPRJ-E2E-${id.toUpperCase()}`;
  const created = await apiCall(page, "POST", "/api/v1/admin/projects", {
    name,
    status: "ongoing",
  });
  expect(created.status(), await created.text()).toBe(201);
  const project = (await created.json()) as { id: string; slug: string };

  const cityId = await sampleCityId(page);
  const patched = await apiCall(page, "PATCH", `/api/v1/admin/projects/${project.id}`, {
    rera_number: rera,
    tagline: "Garden homes for the test suite",
    description: "A *sample* project made by the browser tests.\n\n- Four towers\n- Central garden",
    possession_date: "2029-06-30",
    price: options.priceOnRequest
      ? { on_request: true, min_inr: 7_800_000, max_inr: 12_500_000 }
      : { min_inr: 7_800_000, max_inr: 12_500_000 },
    location: {
      address_line: "Plot 1, Test Sector",
      city_id: cityId,
      pincode: "201301",
      lat: 28.4744,
      lng: 77.504,
      pin_source: "manual",
    },
  });
  expect(patched.status(), await patched.text()).toBe(200);

  const configSlugs: string[] = [];
  for (const [bhk, sqm, priceMin, status] of [
    [2, 66.9, 7_800_000, "available"],
    [3, 104.1, 12_500_000, "sold_out"],
  ] as const) {
    const res = await apiCall(page, "POST", `/api/v1/admin/projects/${project.id}/configurations`, {
      name: `${bhk} BHK (test)`,
      property_type: "apartment",
      bhk,
      area: { min_sqm: sqm, max_sqm: sqm, basis: "carpet", display_unit: "sqft" },
      price: options.priceOnRequest
        ? { on_request: true, min_inr: priceMin }
        : { min_inr: priceMin },
      sales_status: status,
    });
    expect(res.status(), await res.text()).toBe(201);
    configSlugs.push(((await res.json()) as { slug: string }).slug);
  }

  const qr = await apiUpload(page, "/api/v1/admin/media/images", {
    file: sampleQr(),
    title: `${name} QR`,
    attach_to: `project:${project.id}`,
    role: "rera_qr",
  });
  expect(qr.status(), await qr.text()).toBe(201);
  const photo = await apiUpload(page, "/api/v1/admin/media/images", {
    file: samplePhoto(`SAMPLE-${id}-tower.png`, 2),
    title: `${name} tower`,
    alt_text: `${name} towers at dusk`,
    label: "artist_impression",
    attach_to: `project:${project.id}`,
    role: "gallery",
  });
  expect(photo.status(), await photo.text()).toBe(201);

  if (options.publish !== false) {
    const published = await apiCall(page, "POST", `/api/v1/admin/projects/${project.id}/publish`);
    expect(published.status(), await published.text()).toBe(200);
  }
  return { id: project.id, slug: project.slug, name, rera, configSlugs };
}

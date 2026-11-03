/**
 * Server-side public data access layer (Phase 5 Task 5.2, S1, S2).
 *
 * Implements ARCHITECTURE §5 & D-039:
 *   - Typed wrappers for public API endpoints using @empire/api-client.
 *   - Sends only the edge key on cached reads (API server bucket, D-038/D-039); does NOT
 *     send the visitor IP on cached reads so Next.js does not fragment the data cache per IP (S2).
 *   - Applies Next.js fetch cache tags with coarse `content` tag (S1) and 1-hour safety revalidation.
 *   - Maps API 404 to Next.js notFound().
 */
import "server-only";

import { notFound } from "next/navigation";
import { createApiClient, unwrap, type components, type operations } from "@empire/api-client";
import { EDGE_KEY_HEADER } from "@/lib/edge";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";
const SAFETY_REVALIDATE_SECONDS = 3600; // 1 hour safety net fallback
const FETCH_TIMEOUT_MS = 5000;

export type PublicSite = components["schemas"]["PublicSite"];
export type PublicOffer = components["schemas"]["PublicOffer"];
export type PublicProjectList = components["schemas"]["PublicProjectList"];
export type PublicProjectDetail = components["schemas"]["PublicProjectDetail"];
export type PublicPropertyList = components["schemas"]["PublicPropertyList"];
export type PublicPropertyDetail = components["schemas"]["PublicPropertyDetail"];
export type PublicCity = components["schemas"]["PublicCity"];
export type PublicPage = components["schemas"]["PublicPage"];
export type PublicPostList = components["schemas"]["PublicPostList"];
export type PublicPostDetail = components["schemas"]["PublicPost"];
export type PublicFaqList = components["schemas"]["PublicFaq"][];
export type PublicTestimonialList = components["schemas"]["PublicTestimonial"][];
export type PublicRedirect = components["schemas"]["PublicRedirect"];

/**
 * For cached reads, send only the edge key (server bucket) without visitor IP.
 * This ensures Next.js IncrementalCache does not generate separate cache entries per IP (S2).
 */
function getEdgeHeaders(): Record<string, string> {
  const key = process.env.EDGE_PROXY_KEY;
  return key ? { [EDGE_KEY_HEADER]: key } : {};
}

function getClient() {
  return createApiClient({
    baseUrl: API_ORIGIN,
    headers: getEdgeHeaders(),
    // No client timeout: every read passes its own fetch (cachedFetch), which sets the signal.
  });
}

/**
 * The fetch every public read goes through: Next.js data cache with our tags and the 1-hour
 * safety net (ARCHITECTURE §5).
 *
 * WHY a per-request `fetch`: the tags used to go in as `next` options on the call. openapi-fetch
 * copies them onto its Request, but the client's timeout wrapper then called
 * `fetch(request, { signal })`, and Next.js rebuilds a Request when it gets one with an init,
 * which loses the copied `next` (only standard Request fields survive). The data was cached for
 * a year with no tags, so /_internal/revalidate could not clear it. Passing `next`, `cache` and
 * the timeout signal in the init of a fetch we control keeps them (Next reads `init.next`).
 * Tested in test/public-api-cache.test.ts.
 */
export function cachedFetch(tags: string[]): typeof fetch {
  return (input, init) =>
    fetch(input, {
      ...init,
      cache: "force-cache",
      next: { tags, revalidate: SAFETY_REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
}

export async function fetchPublicSite(): Promise<PublicSite> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/site", {
    fetch: cachedFetch(["site", "content"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicProjects(
  query?: operations["public_list_projects"]["parameters"]["query"],
): Promise<PublicProjectList> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/projects", {
    params: { query },
    fetch: cachedFetch(["projects", "content"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicProject(slug: string): Promise<PublicProjectDetail> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/projects/{slug}", {
    params: { path: { slug } },
    fetch: cachedFetch(["projects", `project:${slug}`, "content"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicProperties(
  query?: operations["public_list_properties"]["parameters"]["query"],
): Promise<PublicPropertyList> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/properties", {
    params: { query },
    fetch: cachedFetch(["properties", "content"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

/** One configuration ("property") of a published project (task 5.3). */
export async function fetchPublicProperty(
  slug: string,
  configSlug: string,
): Promise<PublicPropertyDetail> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/projects/{slug}/configurations/{config_slug}", {
    params: { path: { slug, config_slug: configSlug } },
    fetch: cachedFetch(["properties", "projects", `project:${slug}`, "content"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

/**
 * Cities with at least one published project (task 5.3). Tagged `projects` because a project
 * publish, unpublish or move is what changes this list and its counts.
 */
export async function fetchPublicCities(): Promise<PublicCity[]> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/cities", {
    fetch: cachedFetch(["projects", "content"]),
  });
  return unwrap(res);
}

/**
 * A published page by slug, or null when there is none (draft, unknown). For pages a route
 * shows anyway (the home page's holding content, the contact page's forms); other routes use
 * `fetchPublicPage`, which turns a missing page into the site's 404.
 */
export async function fetchPublicPageOrNull(slug: string): Promise<PublicPage | null> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/pages/{slug}", {
    params: { path: { slug } },
    fetch: cachedFetch([`page:${slug}`, "content"]),
  });
  if (res.response.status === 404) return null;
  return unwrap(res);
}

export async function fetchPublicPage(slug: string): Promise<PublicPage> {
  const page = await fetchPublicPageOrNull(slug);
  if (!page) notFound();
  return page;
}

export async function fetchPublicPosts(
  query?: operations["public_list_posts"]["parameters"]["query"],
): Promise<PublicPostList> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/posts", {
    params: { query },
    fetch: cachedFetch(["posts", "content"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicPost(slug: string): Promise<PublicPostDetail> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/posts/{slug}", {
    params: { path: { slug } },
    fetch: cachedFetch(["posts", `post:${slug}`, "content"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicFaqs(
  query?: operations["public_list_faqs"]["parameters"]["query"],
): Promise<PublicFaqList> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/faqs", {
    params: { query },
    fetch: cachedFetch(["faqs", "content"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicTestimonials(
  query?: operations["public_list_testimonials"]["parameters"]["query"],
): Promise<PublicTestimonialList> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/testimonials", {
    params: { query },
    fetch: cachedFetch(["testimonials", "content"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicRedirects(): Promise<PublicRedirect[]> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/redirects", {
    fetch: cachedFetch(["redirects", "site"]),
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

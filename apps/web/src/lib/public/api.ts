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

export type PublicSite = components["schemas"]["PublicSite"];
export type PublicProjectList = components["schemas"]["PublicProjectList"];
export type PublicProjectDetail = components["schemas"]["PublicProjectDetail"];
export type PublicPropertyList = components["schemas"]["PublicPropertyList"];
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
    timeoutMs: 5000,
  });
}

export async function fetchPublicSite(): Promise<PublicSite> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/site", {
    cache: "force-cache",
    next: { tags: ["site", "content"], revalidate: SAFETY_REVALIDATE_SECONDS },
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
    cache: "force-cache",
    next: { tags: ["projects", "content"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicProject(slug: string): Promise<PublicProjectDetail> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/projects/{slug}", {
    params: { path: { slug } },
    cache: "force-cache",
    next: {
      tags: ["projects", `project:${slug}`, "content"],
      revalidate: SAFETY_REVALIDATE_SECONDS,
    },
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
    cache: "force-cache",
    next: { tags: ["properties", "content"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicPage(slug: string): Promise<PublicPage> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/pages/{slug}", {
    params: { path: { slug } },
    cache: "force-cache",
    next: { tags: [`page:${slug}`, "content"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicPosts(
  query?: operations["public_list_posts"]["parameters"]["query"],
): Promise<PublicPostList> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/posts", {
    params: { query },
    cache: "force-cache",
    next: { tags: ["posts", "content"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicPost(slug: string): Promise<PublicPostDetail> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/posts/{slug}", {
    params: { path: { slug } },
    cache: "force-cache",
    next: {
      tags: ["posts", `post:${slug}`, "content"],
      revalidate: SAFETY_REVALIDATE_SECONDS,
    },
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
    cache: "force-cache",
    next: { tags: ["faqs", "content"], revalidate: SAFETY_REVALIDATE_SECONDS },
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
    cache: "force-cache",
    next: { tags: ["testimonials", "content"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicRedirects(): Promise<PublicRedirect[]> {
  const client = getClient();
  const res = await client.GET("/api/v1/public/redirects", {
    cache: "force-cache",
    next: { tags: ["redirects", "site"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

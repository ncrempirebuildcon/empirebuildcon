/**
 * Server-side public data layer for the Empire website (Phase 5 Task 5.2).
 *
 * Implements ARCHITECTURE §3, §5 & D-038:
 *   - Typed calls to 5.1 public endpoints via @empire/api-client.
 *   - Next.js cache tags (`site`, `project:<slug>`, `projects`, `properties`, etc.).
 *   - 1-hour safety revalidate fallback (3600s).
 *   - Edge authentication: sends X-Empire-Edge-Key and visitor X-Empire-Client-IP.
 *   - Static renders without visitor headers use the server rate-limit bucket.
 *   - 404 response invokes Next.js `notFound()`; other failures throw to trigger error.tsx.
 */
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { createApiClient, unwrap, type components, type operations } from "@empire/api-client";
import { edgeHeaders, EDGE_KEY_HEADER } from "@/lib/edge";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";
const SAFETY_REVALIDATE_SECONDS = 3600;

export type PublicSite = components["schemas"]["PublicSite"];
export type PublicProjectList = components["schemas"]["PublicProjectList"];
export type PublicProjectDetail = components["schemas"]["PublicProjectDetail"];
export type PublicPropertyList = components["schemas"]["PublicPropertyList"];
export type PublicPropertyDetail = components["schemas"]["PublicPropertyDetail"];
export type PublicPage = components["schemas"]["PublicPage"];
export type PublicPostList = components["schemas"]["PublicPostList"];
export type PublicPost = components["schemas"]["PublicPost"];
export type PublicFaq = components["schemas"]["PublicFaq"];
export type PublicTestimonial = components["schemas"]["PublicTestimonial"];
export type PublicRedirect = components["schemas"]["PublicRedirect"];

async function getForwardHeaders(): Promise<Record<string, string>> {
  try {
    const h = await headers();
    return edgeHeaders((name) => h.get(name));
  } catch {
    const key = process.env.EDGE_PROXY_KEY;
    return key ? { [EDGE_KEY_HEADER]: key } : {};
  }
}

async function getClient() {
  const reqHeaders = await getForwardHeaders();
  return createApiClient({
    baseUrl: API_ORIGIN,
    headers: reqHeaders,
    timeoutMs: 5000,
  });
}

export async function fetchPublicSite(): Promise<PublicSite> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/site", {
    next: { tags: ["site"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicProjects(
  query?: operations["public_list_projects"]["parameters"]["query"],
): Promise<PublicProjectList> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/projects", {
    params: { query },
    next: { tags: ["projects"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicProject(slug: string): Promise<PublicProjectDetail> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/projects/{slug}", {
    params: { path: { slug } },
    next: { tags: ["projects", `project:${slug}`], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicProperties(
  query?: operations["public_list_properties"]["parameters"]["query"],
): Promise<PublicPropertyList> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/properties", {
    params: { query },
    next: { tags: ["properties"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicProperty(
  projectSlug: string,
  configSlug: string,
): Promise<PublicPropertyDetail> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/projects/{slug}/configurations/{config_slug}", {
    params: { path: { slug: projectSlug, config_slug: configSlug } },
    next: { tags: ["properties", `project:${projectSlug}`], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicPage(slug: string): Promise<PublicPage> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/pages/{slug}", {
    params: { path: { slug } },
    next: { tags: [`page:${slug}`], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicPosts(
  query?: operations["public_list_posts"]["parameters"]["query"],
): Promise<PublicPostList> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/posts", {
    params: { query },
    next: { tags: ["posts"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicPost(slug: string): Promise<PublicPost> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/posts/{slug}", {
    params: { path: { slug } },
    next: { tags: ["posts", `post:${slug}`], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicFaqs(): Promise<PublicFaq[]> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/faqs", {
    next: { tags: ["faqs"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicTestimonials(): Promise<PublicTestimonial[]> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/testimonials", {
    next: { tags: ["testimonials"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

export async function fetchPublicRedirects(): Promise<PublicRedirect[]> {
  const client = await getClient();
  const res = await client.GET("/api/v1/public/redirects", {
    next: { tags: ["redirects", "site"], revalidate: SAFETY_REVALIDATE_SECONDS },
  });
  if (res.response.status === 404) notFound();
  return unwrap(res);
}

/**
 * Turning API errors (RFC 9457 problem+json, handbook/api/openapi-v1.yaml "Problem") into what
 * CMS screens show: one sentence for the page, and a message per form field.
 *
 * Field names arrive dotted ("price.min_inr", "location.city_id"), the same path as the request
 * body, so forms key their errors by those paths.
 */
import { ProblemError, type Problem } from "@empire/api-client";

/** Field path → message, e.g. { "price.min_inr": "Price from must not be more than price up to." } */
export type FieldErrors = Record<string, string>;

const OFFLINE: Problem = {
  title: "Network error",
  status: 0,
  detail: "We couldn't reach the server. Check your connection and try again.",
};

/** The problem behind any thrown value; network failures become status 0. */
export function toProblem(error: unknown): Problem {
  if (error instanceof ProblemError) return error.problem;
  return OFFLINE;
}

/** One sentence for the page, from the API's `detail`, or `fallback` when there is none. */
export function problemMessage(error: unknown, fallback: string): string {
  const problem = toProblem(error);
  if (problem.status === 403) return "Your role can't do this. Ask an admin if you need it.";
  if (problem.status >= 500) return "Something went wrong on our side. Please try again.";
  return problem.detail ?? fallback;
}

/**
 * Field messages from a 422 (or a 409 that names a field, e.g. a slug clash).
 * WHY: Pydantic prefixes custom messages with "Value error, "; staff should only see the sentence.
 */
export function fieldErrors(error: unknown): FieldErrors {
  const out: FieldErrors = {};
  for (const item of toProblem(error).errors ?? []) {
    const message = item.message.replace(/^Value error, /, "");
    out[item.field] ??= message.charAt(0).toUpperCase() + message.slice(1);
  }
  return out;
}

/** True when the session ended (401): the screen should send the user to sign in again. */
export function isSignedOut(error: unknown): boolean {
  return toProblem(error).status === 401;
}

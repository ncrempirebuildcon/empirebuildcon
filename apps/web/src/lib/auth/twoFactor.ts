/**
 * What an answer to the second sign-in step means (POST /auth/2fa/verify and /enrol/confirm,
 * SECURITY.md §1): signed in, a wrong code (try again), a timed-out step (back to the password
 * form), the lockout (429, same counter as passwords, D-027), or no answer at all.
 *
 * WHY the sentence: the API answers 401 both for a wrong code and for a step that timed out
 * (no, expired or used cookie); only its `detail` differs ("Your sign-in timed out…").
 */
import { ProblemError } from "@empire/api-client";

export interface VerifyOutcome {
  result: "ok" | "wrong" | "expired" | "locked" | "offline";
  message?: string;
}

const LOCKED = "Too many attempts. Try again in 15 minutes.";
const TIMED_OUT = /^Your sign-in timed out/;

export function secondStepOutcome(error: unknown): VerifyOutcome {
  if (!(error instanceof ProblemError)) return { result: "offline" };
  const detail = error.problem.detail ?? undefined;
  if (error.status === 429) return { result: "locked", message: detail ?? LOCKED };
  if (error.status === 401 && detail && TIMED_OUT.test(detail)) {
    return { result: "expired", message: detail };
  }
  if (error.status === 401 || error.status === 422) return { result: "wrong", message: detail };
  return { result: "offline", message: detail };
}

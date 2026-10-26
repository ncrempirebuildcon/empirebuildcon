// The second sign-in step (SECURITY.md §1): a wrong code stays on the step, a timed-out step
// goes back to the password form, the lockout shows the API's sentence. The API answers 401 for
// both a wrong code and a timed-out step; only the sentence tells them apart.
import { describe, expect, it } from "vitest";
import { ProblemError } from "@empire/api-client";
import { secondStepOutcome } from "@/lib/auth/twoFactor";

const problem = (status: number, detail: string) =>
  new ProblemError({ type: "about:blank", title: "Error", status, detail });

describe("second sign-in step answers", () => {
  it("tells a wrong code from a timed-out step", () => {
    expect(
      secondStepOutcome(
        problem(401, "That code isn't right. Check your authenticator app and try again."),
      ),
    ).toEqual({
      result: "wrong",
      message: "That code isn't right. Check your authenticator app and try again.",
    });
    expect(
      secondStepOutcome(
        problem(401, "Your sign-in timed out. Enter your email and password again."),
      ).result,
    ).toBe("expired");
  });

  it("shows the lockout and treats anything else as no answer", () => {
    expect(secondStepOutcome(problem(429, "Too many attempts. Try again in 15 minutes."))).toEqual({
      result: "locked",
      message: "Too many attempts. Try again in 15 minutes.",
    });
    expect(secondStepOutcome(new Error("network")).result).toBe("offline");
    expect(secondStepOutcome(problem(500, "Boom")).result).toBe("offline");
  });
});

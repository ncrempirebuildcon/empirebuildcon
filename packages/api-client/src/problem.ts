/**
 * RFC 9457 problem details: the shape of every API error (handbook/api/openapi-v1.yaml, "Problem").
 */

export interface ProblemFieldError {
  field: string;
  message: string;
}

export interface Problem {
  type?: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  errors?: ProblemFieldError[];
}

/** Thrown by `unwrap()` when the API answers with an error. */
export class ProblemError extends Error {
  readonly status: number;
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ProblemError";
    this.status = problem.status;
    this.problem = problem;
  }

  /** Message for one form field, if the API reported one (422 validation errors). */
  fieldError(field: string): string | undefined {
    return this.problem.errors?.find((e) => e.field === field)?.message;
  }
}

/** True when a value looks like a problem+json body. */
export function isProblem(value: unknown): value is Problem {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Problem).status === "number" &&
    typeof (value as Problem).title === "string"
  );
}

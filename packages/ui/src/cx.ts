/** Joins class names, skipping falsy values. Tiny on purpose: no extra dependency for this. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

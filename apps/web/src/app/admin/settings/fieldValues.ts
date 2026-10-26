/**
 * The values behind a Settings form (GroupForm.tsx): the field definitions, the text draft, and
 * the PATCH bodies made from it. Pure functions, so the rules are unit-tested
 * (apps/web/test/settings.test.ts).
 */

export type FieldKind = "text" | "email" | "tel" | "url" | "textarea" | "id" | "number";

export interface FieldDef {
  group: string;
  key: string;
  label: string;
  hint?: string;
  kind: FieldKind;
  placeholder?: string;
  maxLength?: number;
  /** Spans both columns (addresses, long messages). */
  wide?: boolean;
  /** For numbers: the allowed range. */
  min?: number;
  max?: number;
  /**
   * Keep spaces at the start and end (normally trimmed). WHY: the title ending " · Empire" is
   * added straight after a page's title, so its leading space is part of the value (review L3).
   */
  keepSpaces?: boolean;
}

export type GroupValues = Record<string, Record<string, unknown>>;
export type GroupPatches = Record<string, Record<string, unknown>>;

/** A field's id in the draft and in error maps: "group.key". */
export const fieldId = (field: FieldDef) => `${field.group}.${field.key}`;

function toText(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

/** The draft as text, for every field. */
export function draftOf(fields: readonly FieldDef[], values: GroupValues): Record<string, string> {
  return Object.fromEntries(fields.map((f) => [fieldId(f), toText(values[f.group]?.[f.key])]));
}

/**
 * Changed keys per group: text trimmed (unless the field keeps its spaces), empty or blank text
 * as null, numbers as numbers.
 */
export function patchesOf(
  fields: readonly FieldDef[],
  draft: Record<string, string>,
  saved: Record<string, string>,
): GroupPatches {
  const patches: GroupPatches = {};
  for (const field of fields) {
    const id = fieldId(field);
    if (draft[id] === saved[id]) continue;
    const raw = draft[id] ?? "";
    const text = field.keepSpaces ? raw : raw.trim();
    const value = raw.trim() === "" ? null : field.kind === "number" ? Number(text) : text;
    (patches[field.group] ??= {})[field.key] = value;
  }
  return patches;
}

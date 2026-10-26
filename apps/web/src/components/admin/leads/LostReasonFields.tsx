"use client";
/**
 * "Reason (required)" for marking a lead lost (board NoirCmsLead): the fixed list of reasons
 * (`Lead.lost_reason` codes) and "Other reason", which asks for the reason in a few words
 * (`lost_reason_note`). The pipeline rule "lost needs a reason" (ARCHITECTURE §8) is enforced by
 * the API too; this only helps staff give a useful one.
 *
 * WHY codes and not free text: reports can count reasons, and erasure has no free text to hunt
 * for except the note, which it clears.
 */
import { Select, TextField } from "@empire/ui";
import { LOST_REASON, type LostReason } from "@/lib/leads/labels";

export interface LostReasonValue {
  /** A reason code, or "" when nothing is chosen yet. */
  choice: LostReason | "";
  /** The reason in words, needed when `choice` is "other". */
  note: string;
}

export const EMPTY_REASON: LostReasonValue = { choice: "", note: "" };

/** The `lost_reason` and `lost_reason_note` to send, or null when no usable reason was given. */
export function lostReasonBody(
  value: LostReasonValue,
): { lost_reason: LostReason; lost_reason_note: string | null } | null {
  if (!value.choice) return null;
  const note = value.note.trim();
  if (value.choice === "other" && !note) return null;
  return { lost_reason: value.choice, lost_reason_note: value.choice === "other" ? note : null };
}

/** The message for an incomplete reason, or null when it is complete. */
export function lostReasonError(value: LostReasonValue): string | null {
  if (!value.choice) return "Pick a reason to mark this lead lost.";
  if (value.choice === "other" && !value.note.trim()) {
    return "Say in a few words why the lead was lost.";
  }
  return null;
}

export interface LostReasonFieldsProps {
  value: LostReasonValue;
  onChange: (value: LostReasonValue) => void;
  /** The message from `lostReasonError` (or the API) after a save without a full reason. */
  error?: string | null;
  /** Prefix for the field ids, so two forms on one page never clash. */
  idPrefix: string;
  disabled?: boolean;
}

export function LostReasonFields({
  value,
  onChange,
  error,
  idPrefix,
  disabled,
}: LostReasonFieldsProps) {
  const needsWords = value.choice === "other";
  return (
    <div className="flex flex-wrap items-end gap-3">
      <Select
        id={`${idPrefix}-reason`}
        label="Reason"
        required
        placeholder="Choose a reason"
        value={value.choice}
        disabled={disabled}
        options={(Object.keys(LOST_REASON) as LostReason[]).map((code) => ({
          value: code,
          label: LOST_REASON[code],
        }))}
        error={!needsWords || !value.choice ? (error ?? undefined) : undefined}
        onChange={(event) => onChange({ ...value, choice: event.target.value as LostReason | "" })}
        className="min-w-60 flex-[1_1_240px]"
      />
      {needsWords ? (
        <TextField
          id={`${idPrefix}-reason-other`}
          label="Reason in words"
          required
          maxLength={200}
          value={value.note}
          disabled={disabled}
          error={error ?? undefined}
          onChange={(event) => onChange({ ...value, note: event.target.value })}
          className="min-w-60 flex-[1_1_240px]"
        />
      ) : null}
    </div>
  );
}

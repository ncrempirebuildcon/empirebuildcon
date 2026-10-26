/**
 * Words for the read-only integrations status in `GET /admin/settings` (`integrations.email`:
 * Resend connected, not configured, or the development mailbox). No key is ever part of it.
 */
import type { ChipVariant } from "@empire/ui";
import type { SettingsAnswer } from "./useSettings";

export interface EmailStatus {
  chip: ChipVariant;
  label: string;
  detail: string;
}

export function emailStatus(answer: SettingsAnswer | undefined): EmailStatus {
  const status = answer?.integrations.email.status;
  if (status === "connected") {
    return {
      chip: "published",
      label: "Connected",
      detail: "Resend · lead alerts, invites, password resets and security notices.",
    };
  }
  if (status === "dev") {
    return {
      chip: "scheduled",
      label: "Development",
      detail: "Emails go to the development mailbox on the server and are never sent.",
    };
  }
  return {
    chip: "soldOut",
    label: "Not configured",
    detail: "No email can be sent: lead alerts, invites and reset links wait in the queue.",
  };
}

/** "3 emails couldn't be sent in the last 7 days", or null when none failed. */
export function failedEmailsText(count: number): string | null {
  if (count <= 0) return null;
  return `${count} ${count === 1 ? "email" : "emails"} couldn't be sent in the last 7 days.`;
}

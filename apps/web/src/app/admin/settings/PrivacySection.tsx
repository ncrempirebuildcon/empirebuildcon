"use client";
/**
 * Settings → Privacy: how many years leads are kept before the daily clean-up removes their
 * personal details (SECURITY.md §8, ARCHITECTURE §8 "Retention").
 *
 * COMPLIANCE: the retention period is on the owner-approval list, so only the super-admin can
 * change it, within 1 to 10 years; the API enforces both (403 and 422). Changing this screen's
 * rule needs owner approval.
 */
import Link from "next/link";
import { PRIVACY_FIELDS } from "./fields";
import { GroupForm } from "./GroupForm";
import { readOnlyReason, type SectionProps } from "./sections";
import { SETTINGS_PATH } from "@/lib/routes";

export function PrivacySection({ settings, canSave, onDirtyChange }: SectionProps) {
  return (
    <GroupForm
      label="Privacy settings"
      fields={PRIVACY_FIELDS}
      values={settings.groups}
      readOnly={!canSave}
      readOnlyReason={readOnlyReason("privacy", settings)}
      onSave={settings.save}
      onDirtyChange={onDirtyChange}
      before={
        <p className="text-small">
          India&apos;s DPDP law asks us to keep personal data only as long as it&apos;s needed. The
          owner decides this period; changing it is recorded in the audit log. Reading or exporting
          a lead doesn&apos;t count as activity.
        </p>
      }
      after={
        <p className="text-caption text-muted">
          The wording visitors agree to on the forms is under{" "}
          <Link href={`${SETTINGS_PATH}?tab=consent`} className="font-bold underline">
            Consent texts
          </Link>
          . The grievance officer and privacy email are under Contacts.
        </p>
      }
    />
  );
}

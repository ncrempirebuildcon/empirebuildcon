"use client";
/**
 * The body of one Settings section: plain field sections are a GroupForm with their fields
 * (fields.ts); the others have their own components (RERA, lead routing, email and
 * integrations, privacy, consent texts, feature flags).
 */
import { Alert } from "@empire/ui";
import { COMPANY_FIELDS, CONTACT_FIELDS, SEO_FIELDS, TRACKING_FIELDS } from "./fields";
import { GroupForm } from "./GroupForm";
import { ConsentSection } from "./ConsentSection";
import { FlagsSection } from "./FlagsSection";
import { IntegrationsSection } from "./IntegrationsSection";
import { PrivacySection } from "./PrivacySection";
import { ReraSection } from "./ReraSection";
import { RoutingSection } from "./RoutingSection";
import { readOnlyReason, type SectionProps, type SettingsSectionId } from "./sections";

export function SectionBody({ id, ...props }: SectionProps & { id: SettingsSectionId }) {
  const { settings, canSave, onDirtyChange } = props;
  switch (id) {
    case "company":
      return (
        <GroupForm
          label="Company settings"
          fields={COMPANY_FIELDS}
          values={settings.groups}
          readOnly={!canSave}
          readOnlyReason={readOnlyReason(id, settings)}
          onSave={settings.save}
          onDirtyChange={onDirtyChange}
          headings={{ "social.facebook": "Social links" }}
          after={
            <p className="text-caption text-muted">
              The logo files ship with the website (vector brand kit), so changing them is a design
              change, not an upload. The social-share image is set under SEO on each page.
            </p>
          }
        />
      );
    case "contacts":
      return (
        <GroupForm
          label="Contact settings"
          fields={CONTACT_FIELDS}
          values={settings.groups}
          readOnly={!canSave}
          readOnlyReason={readOnlyReason(id, settings)}
          onSave={settings.save}
          onDirtyChange={onDirtyChange}
          before={
            <p className="text-caption text-muted">
              Phone numbers use the same rule as leads: Indian numbers only, landlines with their
              STD code. Emails and phones here are shown on the website once Phase 5 is live.
            </p>
          }
        />
      );
    case "tracking":
      return (
        <GroupForm
          label="Tracking settings"
          fields={TRACKING_FIELDS}
          values={settings.groups}
          readOnly={!canSave}
          readOnlyReason={readOnlyReason(id, settings)}
          onSave={settings.save}
          onDirtyChange={onDirtyChange}
          before={
            <Alert tone="info">
              Each tag loads <strong className="text-ivory">only after the visitor accepts</strong>{" "}
              the matching cookie choice (analytics or marketing). The consent banner and these tags
              arrive in Phase 6; until then nothing loads, even if an ID is filled in.
            </Alert>
          }
        />
      );
    case "seo":
      return (
        <GroupForm
          label="SEO defaults"
          fields={SEO_FIELDS}
          values={settings.groups}
          readOnly={!canSave}
          readOnlyReason={readOnlyReason(id, settings)}
          onSave={settings.save}
          onDirtyChange={onDirtyChange}
          after={
            <div className="flex flex-col gap-1.5 text-small">
              <p>
                <span className="font-semibold text-ivory">Canonical address:</span>{" "}
                https://empirebuildcon.com (fixed; the .in and .co.in addresses redirect here
                permanently).
              </p>
              <p className="text-caption text-muted">
                The sitemap and robots file come with the public site (Phase 5); redirects are under
                Offers &amp; blog → Redirects.
              </p>
            </div>
          }
        />
      );
    case "rera":
      return <ReraSection {...props} />;
    case "routing":
      return <RoutingSection {...props} />;
    case "integrations":
      return <IntegrationsSection {...props} />;
    case "privacy":
      return <PrivacySection {...props} />;
    case "consent":
      return <ConsentSection {...props} />;
    case "flags":
      // Flags save at once (no form), so they have no unsaved changes to report.
      return <FlagsSection />;
  }
}

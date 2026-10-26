"use client";
/**
 * Settings → Email and integrations (board NoirCmsSettings, "Integrations"): whether email can
 * be sent (Resend connected, not configured, or the development mailbox) and how many emails
 * failed lately, the CRM, webhooks and WhatsApp alerts (planned, with the API's notes), and the
 * email sender name and reply-to address. The dashboard's "emails couldn't be sent" task links
 * here (`?tab=integrations`).
 *
 * SECURITY (SECURITY.md §7): keys never appear here. The API reports only a status and the
 * sending address; the key itself is set in the server environment.
 */
import type { ReactNode } from "react";
import { Alert, Chip, type ChipVariant } from "@empire/ui";
import { EMAIL_FIELDS } from "./fields";
import { GroupForm } from "./GroupForm";
import { emailStatus, failedEmailsText } from "./integrations";
import { readOnlyReason, type SectionProps } from "./sections";

export function IntegrationsSection({ settings, canSave, onDirtyChange }: SectionProps) {
  const integrations = settings.data?.integrations;
  const email = emailStatus(settings.data);
  const failed = failedEmailsText(integrations?.email.failed_last_7_days ?? 0);
  return (
    <div className="flex flex-col gap-4.5">
      {failed ? (
        <Alert tone="error" title={failed}>
          They are retried automatically; ones still failing after a day are given up. Check that
          the email service is connected and the addresses are right.
        </Alert>
      ) : null}
      <div className="grid gap-3.5 md:grid-cols-2">
        <StatusCard title="Email sending" chip={email.chip} chipText={email.label}>
          <span className="text-small">{email.detail}</span>
          {integrations?.email.from_address ? (
            <span className="text-caption [overflow-wrap:anywhere] text-muted">
              Sends from {integrations.email.from_address} (set in the server environment).
            </span>
          ) : null}
          <span className="text-caption text-muted">
            API key: set in the server environment, never shown here.
          </span>
        </StatusCard>
        <StatusCard title="CRM" chip="draft" chipText="None">
          <span className="text-small">
            {integrations?.crm.note ?? "The CMS leads pipeline is the CRM at launch."}
          </span>
        </StatusCard>
        <StatusCard title="Webhooks" chip="draft" chipText="Phase 6">
          <span className="text-small">
            {integrations?.webhooks.note ??
              "Signed deliveries to other systems, retried when they are down."}
          </span>
        </StatusCard>
        <StatusCard title="WhatsApp lead alerts" chip="draft" chipText="Phase 6">
          <span className="text-small">
            {integrations?.whatsapp_alerts.note ?? "Needs the WhatsApp Business API."}
          </span>
        </StatusCard>
      </div>
      <p className="text-small text-muted">
        Meta Conversions API and Google Ads conversions come in Phase 6, sent only for leads who
        gave marketing consent, with phone and email hashed.
      </p>
      <GroupForm
        label="Email settings"
        fields={EMAIL_FIELDS}
        values={settings.groups}
        readOnly={!canSave}
        readOnlyReason={readOnlyReason("integrations", settings)}
        onSave={settings.save}
        onDirtyChange={onDirtyChange}
        before={<h3 className="text-base font-bold">How emails are signed</h3>}
      />
    </div>
  );
}

function StatusCard({
  title,
  chip,
  chipText,
  children,
}: {
  title: string;
  chip: ChipVariant;
  chipText: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded-card border border-line-strong bg-noir-700 p-4">
      <span className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-bold">{title}</h3>
        <Chip variant={chip}>{chipText}</Chip>
      </span>
      {children}
    </div>
  );
}

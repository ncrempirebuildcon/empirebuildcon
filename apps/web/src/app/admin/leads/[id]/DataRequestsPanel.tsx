"use client";
/**
 * "Data requests" on the lead detail (board NoirCmsLead), for a super-admin (`leads.erase`):
 * "Erase personal data", after a ConfirmDialog that says exactly what is removed, for which
 * leads, and that it can't be undone.
 *
 * How it works:
 *   1. Erasing covers the lead's whole duplicate group: the enquiry it repeats and every repeat
 *      enquiry (the API follows the links). The dialog names the group it knows about.
 *   2. `same_phone_count` (sent only to a super-admin) counts every lead with this number. When it
 *      is more than the group, the dialog offers one more, unticked box: "Also erase the N other
 *      leads with this phone number", sent as `?scope=person`.
 *   3. Cancel ("Keep the data") is focused first, so Enter by habit never erases anything.
 *
 * COMPLIANCE (DPDP Act, SECURITY.md §8): the dialog's words match the API's erasure
 * (apps/api leads/erasure.py): name and mobile become "[erased]"; email, message, preferred
 * contact time, page and referrer addresses, ad click IDs, UTM term and content, note texts, the
 * lost-reason note and visit notes are removed; the reference, stage history, source and
 * campaign, project and the consent record's version, label and time stay. It is audited.
 */
import { useState } from "react";
import { Alert, Button, Checkbox, ConfirmDialog } from "@empire/ui";
import { api, call } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import type { Lead } from "@/lib/leads/labels";
import { problemMessage } from "@/lib/problems";
import { Panel } from "@/components/admin/states";

/** What the dialog says it erases, and how many leads the duplicate group is known to hold. */
function groupOf(lead: Lead): { text: string; size: number } {
  const repeats = lead.duplicates ?? [];
  if (lead.duplicate_of) {
    return {
      text: `this lead, the first enquiry it repeats (${lead.duplicate_of_reference ?? "linked"}) and every other repeat of that enquiry`,
      size: 2,
    };
  }
  if (repeats.length > 0) {
    const refs = repeats.map((repeat) => repeat.reference).join(", ");
    return {
      text: `this lead and its ${repeats.length === 1 ? "repeat enquiry" : `${repeats.length} repeat enquiries`} (${refs}): ${repeats.length + 1} leads`,
      size: repeats.length + 1,
    };
  }
  return { text: "this lead", size: 1 };
}

export function DataRequestsPanel({ lead, onErased }: { lead: Lead; onErased: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wholePerson, setWholePerson] = useState(false);
  const group = groupOf(lead);
  const samePhone = lead.same_phone_count ?? 0;
  const othersWithPhone = Math.max(samePhone - 1, 0);
  const offerPerson = samePhone > group.size;

  async function erase() {
    setBusy(true);
    setError(null);
    try {
      await call(
        api.DELETE("/api/v1/admin/leads/{id}", {
          params: {
            path: { id: lead.id },
            query: offerPerson && wholePerson ? { scope: "person" } : undefined,
          },
        }),
      );
      setOpen(false);
      onErased();
    } catch (err) {
      setError(problemMessage(err, "Couldn't erase the personal data."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      id="data-requests"
      title="Data requests"
      actions={
        <span className="text-xs font-extrabold tracking-[0.06em] text-gold-400">SUPER-ADMIN</span>
      }
    >
      {lead.erased_at ? (
        <Alert tone="info">
          Personal data erased on {formatDateTime(lead.erased_at)}. The reference, stage history and
          consent record&apos;s metadata are kept for the records.
        </Alert>
      ) : (
        <>
          <p className="text-caption">
            Use only when this person has asked, and you have checked it is them.
          </p>
          <Button
            variant="danger"
            onClick={() => {
              setWholePerson(false);
              setError(null);
              setOpen(true);
            }}
          >
            Erase personal data
          </Button>
          <p className="text-caption text-muted">
            Replaces the personal details with a stub, for this lead and its repeat enquiries. Stage
            history and counts stay for reports. The erasure is written to the audit log. It cannot
            be undone.
          </p>
        </>
      )}
      <ConfirmDialog
        open={open}
        title="Erase this person's data?"
        confirmLabel="Erase personal data"
        cancelLabel="Keep the data"
        tone="danger"
        busy={busy}
        error={error}
        onCancel={() => setOpen(false)}
        onConfirm={() => void erase()}
      >
        <p className="mb-2">
          <strong className="text-ivory">Erases:</strong> {group.text}
          {offerPerson && wholePerson
            ? `, and every other lead with this phone number (${samePhone} leads in all)`
            : ""}
          .
        </p>
        <p className="mb-2">
          <strong className="text-ivory">Removed:</strong> the name and mobile number (both become{" "}
          <span className="whitespace-nowrap">&quot;[erased]&quot;)</span>, the email, the message,
          the preferred contact time, the landing page and referrer addresses, the ad click IDs, the
          UTM term and content, the text of every note, the lost-reason note and the site-visit
          notes.
        </p>
        <p className="mb-2">
          <strong className="text-ivory">Kept:</strong> the reference {lead.reference}, the stage
          and its history, the source and campaign, the project, and the consent record&apos;s text
          version, label and time, so reports still add up.
        </p>
        {offerPerson ? (
          <Checkbox
            className="mb-2"
            checked={wholePerson}
            disabled={busy}
            onChange={(event) => setWholePerson(event.target.checked)}
            label={`Also erase the ${othersWithPhone} other ${othersWithPhone === 1 ? "lead" : "leads"} with this phone number (repeat enquiries included)`}
          />
        ) : null}
        <p>
          The erasure is written to the audit log.{" "}
          <strong className="text-ivory">It cannot be undone.</strong>
        </p>
      </ConfirmDialog>
    </Panel>
  );
}

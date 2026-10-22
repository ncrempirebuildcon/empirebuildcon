"use client";
/**
 * Documents tab (board NoirCmsProject, "Documents"): the RERA QR status, the documents list (media
 * manager, next update) and the RERA designated account, which saves with "Save draft".
 *
 * COMPLIANCE: the RERA QR code is required to publish (D-002). Its upload arrives with the media
 * manager; until then this tab says plainly that it is missing.
 * The designated account details are public on the RERA site, so they are not personal data.
 */
import { TextField } from "@empire/ui";
import { MediaPlaceholder, Panel } from "@/components/admin/states";
import type { FormTabProps } from "./DetailsTab";

export function DocumentsTab({
  form,
  setForm,
  errors,
  canWrite,
  hasQr,
}: FormTabProps & { hasQr: boolean }) {
  return (
    <div className="flex flex-col gap-5">
      <Panel id="rera-qr" title="RERA QR code">
        {hasQr ? (
          <p className="text-small text-palm">The RERA QR code image is uploaded.</p>
        ) : (
          <div className="flex flex-col gap-1 rounded-tile border border-danger bg-danger-bg/20 px-4 py-3.5">
            <strong className="text-ivory">RERA QR code image · missing</strong>
            <span className="text-caption">
              Required to publish. Upload the QR code issued by UP-RERA for this project (PNG or
              JPG). It is shown on the project page with the registration number.
            </span>
          </div>
        )}
        <MediaPlaceholder what="The QR image, RERA certificate, approved plans and brochure are uploaded there." />
      </Panel>

      <fieldset disabled={!canWrite} className="min-w-0">
        <legend className="sr-only">RERA designated account</legend>
        <Panel
          id="rera-account"
          title="RERA designated account"
          description="Shown on the project page. These details are public on the RERA website."
        >
          <div className="grid gap-x-5 gap-y-4 md:grid-cols-3">
            <TextField
              label="Bank"
              maxLength={100}
              value={form.rera_bank_name}
              placeholder="[Bank name]"
              onChange={(e) => setForm({ rera_bank_name: e.target.value })}
              error={errors["rera_account.bank_name"]}
            />
            <TextField
              label="Account name"
              maxLength={120}
              value={form.rera_account_name}
              placeholder="[Account name]"
              onChange={(e) => setForm({ rera_account_name: e.target.value })}
              error={errors["rera_account.account_name"]}
            />
            <TextField
              label="Account number"
              maxLength={40}
              value={form.rera_account_number}
              placeholder="[Account number]"
              onChange={(e) => setForm({ rera_account_number: e.target.value })}
              error={errors["rera_account.account_number"]}
            />
          </div>
        </Panel>
      </fieldset>
    </div>
  );
}

/** Media tab: everything here arrives with the media manager in the next update. */
export function MediaTab() {
  return (
    <Panel
      id="media"
      title="Media manager"
      description="Photos, videos and documents for this project."
    >
      <MediaPlaceholder what="Photos: JPG, PNG, WebP, AVIF up to 10 MB · Videos: MP4 up to 100 MB · Documents: PDF, DOC, PPT up to 10 MB. Label every image honestly: artist's impression, actual photo, or progress photo with its month." />
    </Panel>
  );
}

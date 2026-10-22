"use client";
/**
 * Documents tab (board NoirCmsProject, "Documents"): the RERA QR code panel, the brochure (one
 * PDF) with the "brochure gated" choice, the project's other documents (RERA certificate,
 * approved plans, …), and the RERA designated account.
 *
 * Uploads, replacing and removing save straight away (media manager); the gated choice and the
 * designated account save with "Save draft" like the rest of the project's own fields.
 *
 * COMPLIANCE: the RERA QR code is required to publish (D-002). Its panel says plainly when it is
 * missing; the API refuses to publish without a visible QR, and refuses to remove or hide the QR
 * of a live project ("Upload the new QR first"), so a published project never loses it. The CMS
 * offers only Upload and Replace here: the new QR takes the old one's place in one step, and the
 * old file stays in the library.
 * The QR is uploaded as lossless PNG (long edge 1200 px, resize.ts "qr") and shown on an ivory
 * tile, never under 96 px (DESIGN_SYSTEM §7).
 * The designated account details are public on the RERA site, so they are not personal data.
 */
import { useCallback } from "react";
import { Checkbox, TextField } from "@empire/ui";
import { ACCEPT_PDF, isPdf } from "@/lib/media/files";
import type { AttachRole } from "@/lib/media/upload";
import { Panel } from "@/components/admin/states";
import { LinkedMediaList } from "@/components/admin/media/LinkedMediaList";
import { MediaThumb } from "@/components/admin/media/MediaThumb";
import { SlotUploader } from "@/components/admin/media/SlotUploader";
import type { FormTabProps } from "./DetailsTab";
import type { ProjectAdmin } from "./projectForm";

export interface DocumentsTabProps extends FormTabProps {
  project: ProjectAdmin;
  /** False without `media.upload`: no uploads, replacing or removing. */
  canUpload: boolean;
  onChanged: () => Promise<unknown>;
  reportDirty: (key: string, dirty: boolean) => void;
}

const QR_UPLOAD_ID = "rera-qr-upload";
const BROCHURE_UPLOAD_ID = "brochure-upload";
const DOCUMENT_UPLOAD_ID = "documents-upload";

export function DocumentsTab(props: DocumentsTabProps) {
  const { form, setForm, errors, canWrite, project, canUpload, onChanged, reportDirty } = props;
  // Running uploads count as unsaved changes (leaving would cancel them).
  const qrBusy = useCallback((busy: boolean) => reportDirty("upload-qr", busy), [reportDirty]);
  const brochureBusy = useCallback(
    (busy: boolean) => reportDirty("upload-brochure", busy),
    [reportDirty],
  );
  const documentsBusy = useCallback(
    (busy: boolean) => reportDirty("upload-documents", busy),
    [reportDirty],
  );
  const projectTarget = (role: AttachRole) => ({
    ownerType: "project" as const,
    ownerId: project.id,
    role,
  });
  const brochure = project.brochure ?? null;

  return (
    <div className="flex flex-col gap-5">
      <ReraQrPanel {...props} onBusy={qrBusy} />

      <Panel
        id="brochure"
        title="Brochure"
        description="One PDF. On the website it is the Download brochure button."
      >
        <LinkedMediaList
          idPrefix="brochure"
          items={brochure ? [brochure] : []}
          layout="documents"
          label="Brochure"
          noun="brochure"
          ownerNoun="project"
          reorderable={false}
          canEdit={canUpload}
          onChanged={onChanged}
          focusAfterRemove={BROCHURE_UPLOAD_ID}
          emptyText="No brochure yet."
        />
        {canUpload ? (
          <SlotUploader
            id={BROCHURE_UPLOAD_ID}
            target={projectTarget("brochure")}
            kinds={["document"]}
            accept={ACCEPT_PDF}
            extraCheck={(file) =>
              isPdf(file) ? null : `${file.name}: the brochure must be a PDF.`
            }
            destination="the brochure"
            onUploaded={() => onChanged()}
            reconcile={onChanged}
            onBusyChange={brochureBusy}
          >
            {brochure ? "Replace brochure (PDF)" : "Upload brochure (PDF)"}
          </SlotUploader>
        ) : null}
        <fieldset disabled={!canWrite} className="min-w-0 border-t border-line pt-3">
          <legend className="sr-only">Brochure download</legend>
          <Checkbox
            checked={form.brochure_gated}
            onChange={(e) => setForm({ brochure_gated: e.target.checked })}
            label={
              <>
                <strong className="text-ivory">Brochure gated:</strong> ask for the enquiry form
                before the download. Saved with Save draft. When off, visitors download it straight
                away, no sign-up.
              </>
            }
          />
        </fieldset>
      </Panel>

      <Panel
        id="documents"
        title="Documents"
        description="RERA certificate, approved plans, clearances and progress reports. PDF, DOC or PPT up to 10 MB."
      >
        <LinkedMediaList
          idPrefix="documents-list"
          items={project.documents ?? []}
          layout="documents"
          label="Documents in display order"
          noun="document"
          ownerNoun="project"
          canEdit={canUpload}
          onChanged={onChanged}
          focusAfterRemove={DOCUMENT_UPLOAD_ID}
          emptyText="No documents yet."
        />
        {canUpload ? (
          <SlotUploader
            id={DOCUMENT_UPLOAD_ID}
            target={projectTarget("document")}
            kinds={["document"]}
            multiple
            destination="Documents"
            onUploaded={() => onChanged()}
            reconcile={onChanged}
            onBusyChange={documentsBusy}
          >
            + Upload documents
          </SlotUploader>
        ) : null}
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

function ReraQrPanel({
  project,
  canUpload,
  onChanged,
  onBusy,
}: DocumentsTabProps & { onBusy: (busy: boolean) => void }) {
  const qr = project.rera.qr ?? null;
  const live = project.publish_state === "published";
  const uploader = canUpload ? (
    <SlotUploader
      id={QR_UPLOAD_ID}
      variant={qr ? "secondary" : "primary"}
      target={{ ownerType: "project", ownerId: project.id, role: "rera_qr" }}
      kinds={["image"]}
      accept="image/png,image/jpeg,.png,.jpg,.jpeg"
      extraCheck={(file) =>
        /\.(png|jpe?g)$/i.test(file.name) || ["image/png", "image/jpeg"].includes(file.type)
          ? null
          : `${file.name}: upload the QR code as PNG or JPG.`
      }
      encoding="qr"
      destination="the RERA QR code"
      onUploaded={() => onChanged()}
      reconcile={onChanged}
      onBusyChange={onBusy}
    >
      {qr ? "Replace QR image" : "Upload QR image"}
    </SlotUploader>
  ) : null;

  return (
    <Panel id="rera-qr" title="RERA QR code">
      {qr ? (
        <div className="flex flex-wrap items-center gap-3.5 rounded-tile border border-palm-line px-4 py-3.5">
          {/* COMPLIANCE: ivory tile, at least 96 px, so it stays scannable (DESIGN_SYSTEM §7). */}
          <MediaThumb media={qr} shape="square" ivory className="w-28 shrink-0 rounded-tag" />
          <span className="flex min-w-0 flex-[1_1_240px] flex-col gap-0.5">
            <strong className="text-ivory">RERA QR code image · uploaded</strong>
            <span className="text-caption">
              Shown on the project page with the registration number
              {project.rera.number ? ` ${project.rera.number}` : ""}.
              {live
                ? " This project is live: to change the QR, upload the new one with Replace. It can't be removed or hidden while the project is published."
                : " To change it, upload the new one with Replace; the old file stays in the media library."}
            </span>
          </span>
          {uploader}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3.5 rounded-tile border border-danger bg-danger-bg/20 px-4 py-3.5">
          <span
            aria-hidden="true"
            className="flex size-16 shrink-0 items-center justify-center rounded-tag border-[1.5px] border-dashed border-danger font-extrabold text-danger"
          >
            QR
          </span>
          <span className="flex min-w-0 flex-[1_1_260px] flex-col gap-0.5">
            <strong className="text-ivory">RERA QR code image · missing</strong>
            <span className="text-caption">
              Required to publish. Upload the QR code issued by UP-RERA for this project (PNG or
              JPG). It is shown on the project page with the registration number.
            </span>
          </span>
          {uploader}
        </div>
      )}
    </Panel>
  );
}

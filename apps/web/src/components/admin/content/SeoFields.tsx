"use client";
/**
 * The SEO fields of a page or post (board NoirCmsProject's SEO tab, reused): search title and
 * description with character counts, canonical path, noindex, the share image, a search-result
 * preview, and the API's checklist (`seo_warnings`: missing or too-long title and description).
 *
 * The checklist describes the saved version (the API computes it), so it says "as last saved";
 * the counts under the fields react while typing.
 *
 * SECURITY: the fields need `seo.manage` (ARCHITECTURE §11); without it they are read-only. The
 * API validates every value again (title ≤ 70, description ≤ 170, an image for the share image,
 * a path on this site for the canonical path).
 */
import { CharacterCount, Checkbox, TextField, Textarea } from "@empire/ui";
import type { Schema } from "@/lib/api";
import type { SeoForm } from "@/lib/content/seo";
import type { FieldErrors } from "@/lib/problems";
import { Panel } from "@/components/admin/states";
import { MediaField } from "@/components/admin/media/MediaField";

/** Recommended lengths (the API's hard limits are 70 and 170). */
export const SEO_TITLE_LIMIT = 60;
export const SEO_DESCRIPTION_LIMIT = 160;

export interface SeoFieldsProps {
  value: SeoForm;
  onChange: (patch: Partial<SeoForm>) => void;
  /** Field errors keyed "seo.title", "seo.description", … from the API or the form's checks. */
  errors: FieldErrors;
  /** The API's checklist for the saved version. */
  warnings: readonly Schema<"SeoWarning">[];
  /** The address on the website, e.g. "/about" (for the preview and the canonical hint). */
  path: string;
  /** What search engines show when the title is empty, e.g. "About | Empire". */
  fallbackTitle: string;
  fallbackDescription: string;
  /** With `seo.manage`. */
  canEdit: boolean;
  /** With `media.upload`: the share image can be uploaded, not only chosen. */
  canUpload: boolean;
  /** Extra words under "Hide from search engines", e.g. for campaign pages. */
  noindexHint?: string;
  onBusyChange?: (busy: boolean) => void;
}

export function SeoFields({
  value,
  onChange,
  errors,
  warnings,
  path,
  fallbackTitle,
  fallbackDescription,
  canEdit,
  canUpload,
  noindexHint,
  onBusyChange,
}: SeoFieldsProps) {
  const previewTitle = value.title.trim() || fallbackTitle;
  const previewDescription = value.description.trim() || fallbackDescription;
  const crumbs = path === "/" ? "" : path.split("/").filter(Boolean).join(" › ");
  return (
    <Panel id="seo" title="Search engines and sharing">
      <section aria-labelledby="seo-checklist-title" className="flex flex-col gap-2">
        <h3 id="seo-checklist-title" className="text-small font-bold text-ivory">
          SEO checklist <span className="font-normal text-muted">(as last saved)</span>
        </h3>
        {warnings.length === 0 ? (
          <p className="flex items-center gap-2 text-small">
            <Mark ok /> <span>Title and description are set and within the limits.</span>
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5" aria-label="SEO warnings">
            {warnings.map((warning) => (
              <li key={warning.code} className="flex items-start gap-2 text-small">
                <Mark ok={false} /> <span>{warning.message}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <fieldset disabled={!canEdit} className="min-w-0">
        <legend className="sr-only">Search engine fields</legend>
        {!canEdit ? (
          <p className="mb-3 text-caption text-muted">
            Editing these needs the seo.manage permission.
          </p>
        ) : null}
        <div className="flex flex-wrap gap-5">
          <div className="flex min-w-0 flex-[1.2_1_320px] flex-col gap-4">
            <TextField
              label="Search title"
              maxLength={70}
              value={value.title}
              placeholder={fallbackTitle}
              onChange={(event) => onChange({ title: event.target.value })}
              error={errors["seo.title"]}
              hint={<CharacterCount value={value.title} limit={SEO_TITLE_LIMIT} />}
            />
            <Textarea
              label="Search description"
              rows={3}
              maxLength={170}
              value={value.description}
              onChange={(event) => onChange({ description: event.target.value })}
              error={errors["seo.description"]}
              hint={<CharacterCount value={value.description} limit={SEO_DESCRIPTION_LIMIT} />}
            />
            <TextField
              label="Canonical path"
              maxLength={200}
              value={value.canonical_path}
              placeholder={path}
              onChange={(event) => onChange({ canonical_path: event.target.value })}
              error={errors["seo.canonical_path"]}
              hint="Always on empirebuildcon.com. Leave empty to use this page's own address."
            />
            <Checkbox
              checked={value.noindex}
              onChange={(event) => onChange({ noindex: event.target.checked })}
              label="Hide from search engines (noindex)"
              hint={noindexHint}
            />
          </div>
          <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-4">
            <MediaField
              id="seo-share-image"
              label="Share image (1200 × 630)"
              kind="image"
              value={value.og_image}
              missingPreview={Boolean(value.og_image_id) && !value.og_image}
              onChange={(media) => onChange({ og_image: media, og_image_id: media?.id ?? "" })}
              canUpload={canUpload}
              disabled={!canEdit}
              error={errors["seo.og_image_id"]}
              hint="Shown when the page is shared on WhatsApp or social media."
              onBusyChange={onBusyChange}
            />
            <figure className="flex flex-col gap-1 rounded-tile border border-line bg-noir-900 p-3.5">
              <figcaption className="text-xs font-bold tracking-[0.08em] text-muted">
                SEARCH PREVIEW
              </figcaption>
              <span className="text-xs text-muted">
                empirebuildcon.com{crumbs ? ` › ${crumbs}` : ""}
              </span>
              <strong className="text-base leading-snug text-gold-300">{previewTitle}</strong>
              <span className="text-caption">{previewDescription}</span>
            </figure>
          </div>
        </div>
      </fieldset>
    </Panel>
  );
}

function Mark({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`flex size-5 shrink-0 items-center justify-center rounded-pill text-xs font-extrabold ${
        ok ? "bg-palm-line/30 text-palm" : "bg-danger/20 text-danger"
      }`}
    >
      {ok ? "✓" : "!"}
    </span>
  );
}

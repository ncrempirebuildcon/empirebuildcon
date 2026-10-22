"use client";
/**
 * SEO tab (board NoirCmsProject, "SEO"): search title and description with character counts,
 * the canonical path, noindex, the share image (ShareImagePicker.tsx) and a preview of the search
 * result. Saved with "Save draft".
 */
import { CharacterCount, Checkbox, TextField, Textarea } from "@empire/ui";
import { Panel } from "@/components/admin/states";
import type { FormTabProps } from "./DetailsTab";
import type { ProjectAdmin } from "./projectForm";
import { ShareImagePicker } from "./ShareImagePicker";

export interface SeoTabProps extends FormTabProps {
  project: ProjectAdmin;
  /** False without `media.upload`: the share image can be picked but not uploaded. */
  canUpload: boolean;
  reportDirty: (key: string, dirty: boolean) => void;
}

const TITLE_LIMIT = 60;
const DESCRIPTION_LIMIT = 160;

export function SeoTab({
  form,
  setForm,
  errors,
  canWrite,
  project,
  canUpload,
  reportDirty,
}: SeoTabProps) {
  const slug = form.slug.trim() || "[web-address]";
  const previewTitle = form.seo_title.trim() || `${form.name.trim() || "[Project name]"} | Empire`;
  const previewDescription =
    form.seo_description.trim() || form.tagline.trim() || "[Search description]";
  return (
    <fieldset disabled={!canWrite} className="min-w-0">
      <legend className="sr-only">Search engines</legend>
      <Panel id="seo" title="Search engines">
        <div className="flex flex-wrap gap-5">
          <div className="flex min-w-0 flex-[1.2_1_360px] flex-col gap-4">
            <TextField
              label="Search title"
              maxLength={70}
              value={form.seo_title}
              placeholder={previewTitle}
              onChange={(e) => setForm({ seo_title: e.target.value })}
              error={errors["seo.title"]}
              hint={<CharacterCount value={form.seo_title} limit={TITLE_LIMIT} />}
            />
            <Textarea
              label="Search description"
              rows={3}
              maxLength={170}
              value={form.seo_description}
              onChange={(e) => setForm({ seo_description: e.target.value })}
              error={errors["seo.description"]}
              hint={<CharacterCount value={form.seo_description} limit={DESCRIPTION_LIMIT} />}
            />
            <TextField
              label="Canonical path"
              maxLength={200}
              value={form.seo_canonical_path}
              placeholder={`/projects/${slug}`}
              onChange={(e) => setForm({ seo_canonical_path: e.target.value })}
              error={errors["seo.canonical_path"]}
              hint="Always on empirebuildcon.com. Leave empty to use the project's own address."
            />
            <Checkbox
              checked={form.seo_noindex}
              onChange={(e) => setForm({ seo_noindex: e.target.checked })}
              label="Hide from search engines (noindex)"
            />
          </div>
          <div className="flex min-w-0 flex-[1_1_280px] flex-col gap-4">
            <ShareImagePicker
              project={project}
              value={form.seo_og_image_id}
              onChange={(id) => setForm({ seo_og_image_id: id })}
              canWrite={canWrite}
              canUpload={canUpload}
              reportDirty={reportDirty}
              error={errors["seo.og_image_id"]}
            />
            <figure className="flex flex-col gap-1 rounded-tile border border-line bg-noir-900 p-3.5">
              <figcaption className="text-xs font-bold tracking-[0.08em] text-muted">
                SEARCH PREVIEW
              </figcaption>
              <span className="text-xs text-muted">empirebuildcon.com › projects › {slug}</span>
              <strong className="text-base leading-snug text-gold-300">{previewTitle}</strong>
              <span className="text-caption">{previewDescription}</span>
            </figure>
          </div>
        </div>
      </Panel>
    </fieldset>
  );
}

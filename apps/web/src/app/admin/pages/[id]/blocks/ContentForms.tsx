"use client";
/**
 * Settings forms for the blocks that hold their own content: hero, text, image, gallery, video,
 * call to action, steps and columns (board NoirCmsPage, "Block settings"). Field limits follow
 * the API (content/blocks.py); formatted text uses FormattedTextEditor with a live preview.
 */
import { FormattedTextEditor, SegmentedControl, TextField, Textarea } from "@empire/ui";
import type { Media } from "@/lib/media/upload";
import { GalleryField, MediaField } from "@/components/admin/media/MediaField";
import type { DataOf } from "./blockDraft";
import {
  ButtonFields,
  ItemsEditor,
  OptionalText,
  orNull,
  useBlockMedia,
  type BlockFormProps,
} from "./fields";

/** A stand-in for a library item whose details weren't loaded (gallery previews). */
function placeholder(id: string): Media {
  return {
    id,
    title: "Photo (preview not available)",
    alt_text: null,
    kind: "image",
    format: "",
    url: "",
    thumbnail_url: null,
    bytes: 0,
    width: null,
    height: null,
    duration_s: null,
    label: null,
    label_month: null,
    is_sample: false,
    attached_count: 0,
    created_at: "",
  } as Media;
}

export function HeroForm({
  data,
  onChange,
  errors,
  idPrefix,
  canUpload,
  onBusyChange,
}: BlockFormProps<DataOf<"hero">>) {
  const media = useBlockMedia();
  const set = (patch: Partial<DataOf<"hero">>) => onChange({ ...data, ...patch });
  const image = media.get(data.image_id);
  return (
    <>
      <OptionalText
        id={`${idPrefix}-eyebrow`}
        label="Eyebrow"
        maxLength={60}
        value={data.eyebrow}
        onChange={(eyebrow) => set({ eyebrow })}
        error={errors.eyebrow}
        hint="A short line above the heading, e.g. [UTTAR PRADESH · RESIDENCES]."
      />
      <TextField
        id={`${idPrefix}-heading`}
        label="Heading"
        required
        maxLength={120}
        value={data.heading}
        onChange={(event) => set({ heading: event.target.value })}
        error={errors.heading}
        hint={`${[...data.heading].length} characters · keep it under 40`}
      />
      <Textarea
        id={`${idPrefix}-subheading`}
        label="Intro text (optional)"
        rows={3}
        maxLength={500}
        value={data.subheading ?? ""}
        onChange={(event) => set({ subheading: orNull(event.target.value) })}
        error={errors.subheading}
      />
      <MediaField
        id={`${idPrefix}-image`}
        label="Image"
        kind="image"
        labelRequired
        value={image}
        missingPreview={Boolean(data.image_id) && !image}
        onChange={(chosen) => {
          if (chosen) media.remember(chosen);
          set({ image_id: chosen?.id ?? null });
        }}
        canUpload={canUpload}
        error={errors.image_id}
        hint="Photos show their honest label on the website (artist's impression or actual photo)."
        onBusyChange={onBusyChange}
      />
      <ButtonFields
        legend="Main button"
        optional
        value={data.cta ?? null}
        onChange={(cta) => set({ cta })}
        errors={errors}
        prefix="cta"
        idPrefix={idPrefix}
      />
      <ButtonFields
        legend="Second button"
        optional
        value={data.secondary_cta ?? null}
        onChange={(secondary_cta) => set({ secondary_cta })}
        errors={errors}
        prefix="secondary_cta"
        idPrefix={idPrefix}
      />
    </>
  );
}

export function RichTextForm({
  data,
  onChange,
  errors,
  idPrefix,
}: BlockFormProps<DataOf<"rich_text">>) {
  return (
    <>
      <OptionalText
        id={`${idPrefix}-heading`}
        label="Heading"
        maxLength={120}
        value={data.heading}
        onChange={(heading) => onChange({ ...data, heading })}
        error={errors.heading}
      />
      <FormattedTextEditor
        id={`${idPrefix}-body`}
        label="Text"
        required
        rows={8}
        limit={50000}
        value={data.body}
        onChange={(body) => onChange({ ...data, body })}
        error={errors.body}
      />
    </>
  );
}

export function ImageForm({
  data,
  onChange,
  errors,
  idPrefix,
  canUpload,
  onBusyChange,
}: BlockFormProps<DataOf<"image">>) {
  const media = useBlockMedia();
  const image = media.get(data.image_id);
  return (
    <>
      <MediaField
        id={`${idPrefix}-image`}
        label="Photo"
        kind="image"
        labelRequired
        value={image}
        missingPreview={Boolean(data.image_id) && !image}
        onChange={(chosen) => {
          if (chosen) media.remember(chosen);
          onChange({ ...data, image_id: chosen?.id ?? "" });
        }}
        canUpload={canUpload}
        error={errors.image_id}
        onBusyChange={onBusyChange}
      />
      <OptionalText
        id={`${idPrefix}-caption`}
        label="Caption"
        maxLength={250}
        value={data.caption}
        onChange={(caption) => onChange({ ...data, caption })}
        error={errors.caption}
      />
    </>
  );
}

export function GalleryForm({
  data,
  onChange,
  errors,
  idPrefix,
  canUpload,
  onBusyChange,
}: BlockFormProps<DataOf<"gallery">>) {
  const media = useBlockMedia();
  return (
    <>
      <OptionalText
        id={`${idPrefix}-heading`}
        label="Heading"
        maxLength={120}
        value={data.heading}
        onChange={(heading) => onChange({ ...data, heading })}
        error={errors.heading}
      />
      <GalleryField
        id={`${idPrefix}-images`}
        label="Photos"
        max={24}
        labelRequired
        value={data.image_ids.map((id) => media.get(id) ?? placeholder(id))}
        onChange={(items) => {
          items.forEach(media.remember);
          onChange({ ...data, image_ids: items.map((item) => item.id) });
        }}
        canUpload={canUpload}
        error={errors.image_ids}
        onBusyChange={onBusyChange}
      />
    </>
  );
}

export function VideoForm({
  data,
  onChange,
  errors,
  idPrefix,
  canUpload,
  onBusyChange,
}: BlockFormProps<DataOf<"video">>) {
  const media = useBlockMedia();
  const fromLink = data.url !== null && data.url !== undefined;
  const video = media.get(data.media_id);
  return (
    <>
      <OptionalText
        id={`${idPrefix}-heading`}
        label="Heading"
        maxLength={120}
        value={data.heading}
        onChange={(heading) => onChange({ ...data, heading })}
        error={errors.heading}
      />
      <SegmentedControl
        label="Where the video comes from"
        value={fromLink ? "link" : "library"}
        options={[
          { value: "library", label: "From the library" },
          { value: "link", label: "YouTube or Vimeo link" },
        ]}
        onChange={(source) =>
          onChange(
            source === "link"
              ? { ...data, media_id: null, url: data.url ?? "" }
              : { ...data, url: null },
          )
        }
      />
      {errors[""] ? <p className="text-caption text-danger">{errors[""]}</p> : null}
      {fromLink ? (
        <TextField
          id={`${idPrefix}-url`}
          label="Video link"
          maxLength={500}
          value={data.url ?? ""}
          placeholder="https://www.youtube.com/watch?v=[video id]"
          onChange={(event) => onChange({ ...data, url: event.target.value })}
          error={errors.url}
          hint="Only YouTube and Vimeo links are accepted. The page stores the video's id, not the link you paste."
        />
      ) : (
        <MediaField
          id={`${idPrefix}-video`}
          label="Video"
          kind="video"
          value={video}
          missingPreview={Boolean(data.media_id) && !video}
          onChange={(chosen) => {
            if (chosen) media.remember(chosen);
            onChange({ ...data, media_id: chosen?.id ?? null });
          }}
          canUpload={canUpload}
          error={errors.media_id}
          onBusyChange={onBusyChange}
        />
      )}
      <OptionalText
        id={`${idPrefix}-caption`}
        label="Caption"
        maxLength={250}
        value={data.caption}
        onChange={(caption) => onChange({ ...data, caption })}
        error={errors.caption}
      />
    </>
  );
}

export function CtaForm({ data, onChange, errors, idPrefix }: BlockFormProps<DataOf<"cta">>) {
  return (
    <>
      <OptionalText
        id={`${idPrefix}-heading`}
        label="Heading"
        maxLength={120}
        value={data.heading}
        onChange={(heading) => onChange({ ...data, heading })}
        error={errors.heading}
      />
      <Textarea
        id={`${idPrefix}-text`}
        label="Text (optional)"
        rows={2}
        maxLength={500}
        value={data.text ?? ""}
        onChange={(event) => onChange({ ...data, text: orNull(event.target.value) })}
        error={errors.text}
      />
      <ButtonFields
        legend="Button"
        value={{ label: data.label, href: data.href }}
        onChange={(button) =>
          onChange({ ...data, label: button?.label ?? "", href: button?.href ?? "" })
        }
        errors={errors}
        prefix=""
        idPrefix={idPrefix}
      />
    </>
  );
}

export function StepsForm({ data, onChange, errors, idPrefix }: BlockFormProps<DataOf<"steps">>) {
  return (
    <>
      <OptionalText
        id={`${idPrefix}-heading`}
        label="Heading"
        maxLength={120}
        value={data.heading}
        onChange={(heading) => onChange({ ...data, heading })}
        error={errors.heading}
      />
      <ItemsEditor
        items={data.items}
        onChange={(items) => onChange({ ...data, items })}
        noun="Step"
        min={1}
        max={8}
        make={() => ({ title: "", text: null })}
        addLabel="+ Add step"
        render={(item, index, set) => (
          <>
            <TextField
              id={`${idPrefix}-items-${index}-title`}
              label="Title"
              required
              maxLength={80}
              value={item.title}
              onChange={(event) => set({ title: event.target.value })}
              error={errors[`items.${index}.title`]}
            />
            <Textarea
              id={`${idPrefix}-items-${index}-text`}
              label="Text (optional)"
              rows={2}
              maxLength={500}
              value={item.text ?? ""}
              onChange={(event) => set({ text: orNull(event.target.value) })}
              error={errors[`items.${index}.text`]}
            />
          </>
        )}
      />
    </>
  );
}

export function ColumnsForm({
  data,
  onChange,
  errors,
  idPrefix,
}: BlockFormProps<DataOf<"columns">>) {
  return (
    <>
      <OptionalText
        id={`${idPrefix}-heading`}
        label="Heading"
        maxLength={120}
        value={data.heading}
        onChange={(heading) => onChange({ ...data, heading })}
        error={errors.heading}
      />
      <ItemsEditor
        items={data.columns}
        onChange={(columns) => onChange({ ...data, columns })}
        noun="Column"
        min={2}
        max={3}
        make={() => ({ heading: null, body: "" })}
        addLabel="+ Add a third column"
        render={(column, index, set) => (
          <>
            <OptionalText
              id={`${idPrefix}-columns-${index}-heading`}
              label="Heading"
              maxLength={80}
              value={column.heading}
              onChange={(heading) => set({ heading })}
              error={errors[`columns.${index}.heading`]}
            />
            <FormattedTextEditor
              id={`${idPrefix}-columns-${index}-body`}
              label={`Column ${index + 1} text`}
              required
              rows={5}
              limit={5000}
              value={column.body}
              onChange={(body) => set({ body })}
              error={errors[`columns.${index}.body`]}
            />
          </>
        )}
      />
    </>
  );
}

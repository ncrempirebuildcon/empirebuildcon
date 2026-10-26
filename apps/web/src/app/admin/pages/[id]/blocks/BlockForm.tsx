"use client";
/**
 * Picks the settings form for a block's type. Each form edits the block's `data` only; showing,
 * hiding, moving and deleting live in the block list (BlocksTab.tsx).
 */
import type { FieldErrors } from "@/lib/problems";
import { emptyPickNote, type DraftBlock } from "./blockDraft";
import {
  ColumnsForm,
  CtaForm,
  GalleryForm,
  HeroForm,
  ImageForm,
  RichTextForm,
  StepsForm,
  VideoForm,
} from "./ContentForms";
import { OfferBannerForm, StatsForm, TestimonialsForm } from "./HonestyForms";
import { FaqListForm, GridForm, LeadFormForm, MapForm } from "./ReferenceForms";

export interface BlockFormSwitchProps {
  block: DraftBlock;
  onChange: (block: DraftBlock) => void;
  errors: FieldErrors;
  canUpload: boolean;
  onBusyChange: (busy: boolean) => void;
}

export function BlockForm(props: BlockFormSwitchProps) {
  const note = emptyPickNote(props.block);
  return (
    <>
      {note ? (
        <p className="rounded-tile border border-line-strong bg-noir-700 px-3.5 py-2.5 text-caption text-ivory">
          {note}
        </p>
      ) : null}
      <TypeForm {...props} />
    </>
  );
}

function TypeForm({ block, onChange, errors, canUpload, onBusyChange }: BlockFormSwitchProps) {
  const common = { errors, canUpload, onBusyChange, idPrefix: `block-${block.key}` };
  switch (block.type) {
    case "hero":
      return (
        <HeroForm {...common} data={block.data} onChange={(data) => onChange({ ...block, data })} />
      );
    case "rich_text":
      return (
        <RichTextForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "image":
      return (
        <ImageForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "gallery":
      return (
        <GalleryForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "video":
      return (
        <VideoForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "project_grid":
    case "property_grid": {
      const type = block.type;
      return (
        <GridForm
          {...common}
          kind={type}
          data={block.data}
          onChange={(data) => onChange({ ...block, type, data })}
        />
      );
    }
    case "cta":
      return (
        <CtaForm {...common} data={block.data} onChange={(data) => onChange({ ...block, data })} />
      );
    case "lead_form":
      return (
        <LeadFormForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "faq_list":
      return (
        <FaqListForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "stats":
      return (
        <StatsForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "testimonials":
      return (
        <TestimonialsForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "offer_banner":
      return (
        <OfferBannerForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "map":
      return (
        <MapForm {...common} data={block.data} onChange={(data) => onChange({ ...block, data })} />
      );
    case "steps":
      return (
        <StepsForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "columns":
      return (
        <ColumnsForm
          {...common}
          data={block.data}
          onChange={(data) => onChange({ ...block, data })}
        />
      );
    case "divider":
      return <p className="text-small text-muted">A divider has no settings.</p>;
  }
}

"use client";
/**
 * A rough preview of the selected block (board NoirCmsPage, "Preview"): the block's own words,
 * images and numbers in the site's type and colours, so staff can check what they typed. It is
 * not the public page (that rendering arrives in Phase 5, TODO(phase-5)): lists of projects,
 * FAQs or offers show what they will contain, in [brackets], instead of live data.
 *
 * Buttons inside the preview are drawn, not real, so nothing here can be clicked by mistake.
 * Formatted text goes through `FormattedText`, the same safe renderer the website will use.
 */
import type { ReactNode } from "react";
import { FormattedText, cx } from "@empire/ui";
import { formatCalendarDate } from "@/lib/dates";
import { MediaThumb } from "@/components/admin/media/MediaThumb";
import { BLOCK_TYPES } from "@/lib/content/blockTypes";
import { LEAD_SOURCE } from "@/lib/leads/labels";
import { OFFER_PLACEMENT } from "@/lib/content/labels";
import type { DraftBlock } from "./blockDraft";
import { useBlockMedia } from "./fields";

function Heading({ children }: { children: ReactNode }) {
  return <p className="font-display text-2xl font-semibold text-ivory">{children}</p>;
}

function FakeButton({ children, secondary = false }: { children: ReactNode; secondary?: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex min-h-10 items-center rounded-pill px-4 text-small font-bold",
        secondary ? "border border-gold-500 text-gold-300" : "bg-gold-500 text-noir-900",
      )}
    >
      {children}
    </span>
  );
}

function Placeholder({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-tile border border-dashed border-line-strong px-4 py-6 text-center text-caption text-muted">
      {children}
    </p>
  );
}

function Body({ block }: { block: DraftBlock }) {
  const media = useBlockMedia();
  switch (block.type) {
    case "hero": {
      const image = media.get(block.data.image_id);
      return (
        <div className="flex flex-wrap items-center gap-5">
          <div className="flex min-w-0 flex-[1_1_240px] flex-col gap-3">
            {block.data.eyebrow ? (
              <p className="text-xs font-bold tracking-[0.18em] text-gold-400">
                {block.data.eyebrow}
              </p>
            ) : null}
            <p className="font-display text-3xl leading-tight font-semibold text-ivory">
              {block.data.heading || "[Heading]"}
            </p>
            {block.data.subheading ? <p className="text-small">{block.data.subheading}</p> : null}
            <div className="flex flex-wrap gap-2">
              {block.data.cta ? <FakeButton>{block.data.cta.label}</FakeButton> : null}
              {block.data.secondary_cta ? (
                <FakeButton secondary>{block.data.secondary_cta.label}</FakeButton>
              ) : null}
            </div>
          </div>
          {image ? (
            <MediaThumb media={image} className="w-full max-w-64 rounded-t-[999px]" />
          ) : null}
        </div>
      );
    }
    case "rich_text":
      return (
        <div className="flex flex-col gap-3 text-small">
          {block.data.heading ? <Heading>{block.data.heading}</Heading> : null}
          <FormattedText text={block.data.body} empty={<Placeholder>[Text]</Placeholder>} />
        </div>
      );
    case "image": {
      const image = media.get(block.data.image_id);
      return (
        <figure className="flex flex-col gap-2">
          {image ? (
            <MediaThumb media={image} className="w-full rounded-tile" />
          ) : (
            <Placeholder>[Photo]</Placeholder>
          )}
          {block.data.caption ? (
            <figcaption className="text-caption text-muted">{block.data.caption}</figcaption>
          ) : null}
        </figure>
      );
    }
    case "gallery":
      return (
        <div className="flex flex-col gap-3">
          {block.data.heading ? <Heading>{block.data.heading}</Heading> : null}
          {block.data.image_ids.length === 0 ? (
            <Placeholder>[Photos]</Placeholder>
          ) : (
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(110px,1fr))] gap-2">
              {block.data.image_ids.map((id) => {
                const image = media.get(id);
                return (
                  <li key={id}>
                    {image ? (
                      <MediaThumb media={image} className="rounded-tag" />
                    ) : (
                      <span className="block aspect-[4/3] rounded-tag bg-noir-700" />
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      );
    case "video": {
      const video = media.get(block.data.media_id);
      return (
        <div className="flex flex-col gap-3">
          {block.data.heading ? <Heading>{block.data.heading}</Heading> : null}
          {video ? (
            <MediaThumb media={video} shape="video" className="w-full rounded-tile" />
          ) : (
            <Placeholder>
              {block.data.url
                ? `[Video player for ${block.data.url}]`
                : "[Video from the library or a YouTube/Vimeo link]"}
            </Placeholder>
          )}
          {block.data.caption ? (
            <p className="text-caption text-muted">{block.data.caption}</p>
          ) : null}
        </div>
      );
    }
    case "project_grid":
    case "property_grid":
      return (
        <div className="flex flex-col gap-3">
          {block.data.heading ? <Heading>{block.data.heading}</Heading> : null}
          {block.data.show_status_tabs ? (
            <div className="flex gap-2 text-caption" aria-hidden="true">
              <FakeButton secondary>All</FakeButton>
              <FakeButton secondary>Ongoing</FakeButton>
              <FakeButton secondary>Completed</FakeButton>
            </div>
          ) : null}
          <Placeholder>
            [Up to {block.data.limit} {block.type === "project_grid" ? "project" : "property"} cards
            {block.data.featured_only ? ", featured only" : ""}. Each card shows its UP-RERA number,
            price range with the GST and stamp duty note, and carpet area first.]
          </Placeholder>
        </div>
      );
    case "cta":
      return (
        <div className="flex flex-col items-start gap-3">
          {block.data.heading ? <Heading>{block.data.heading}</Heading> : null}
          {block.data.text ? <p className="text-small">{block.data.text}</p> : null}
          <FakeButton>{block.data.label || "[Button text]"}</FakeButton>
        </div>
      );
    case "lead_form":
      return (
        <div className="flex flex-col gap-3">
          <Heading>{block.data.heading || "[Form heading]"}</Heading>
          {block.data.intro ? <p className="text-small">{block.data.intro}</p> : null}
          <div aria-hidden="true" className="flex flex-col gap-2">
            <span className="rounded-input border border-field-line px-3 py-2 text-caption text-muted">
              Name
            </span>
            <span className="rounded-input border border-field-line px-3 py-2 text-caption text-muted">
              Mobile
            </span>
          </div>
          <p className="text-caption text-muted">
            [Current consent text, with separate unticked boxes] · {LEAD_SOURCE[block.data.source]}
          </p>
        </div>
      );
    case "faq_list":
      return (
        <div className="flex flex-col gap-3">
          <Heading>{block.data.heading || "Frequently asked questions"}</Heading>
          <Placeholder>
            {(block.data.faq_ids ?? []).length > 0
              ? `[${(block.data.faq_ids ?? []).length} chosen questions with their answers]`
              : block.data.project_id
                ? "[The project's FAQs set to show on the website]"
                : "[Site-wide FAQs set to show on the website]"}
          </Placeholder>
        </div>
      );
    case "stats":
      return (
        <div className="flex flex-col gap-3">
          {block.data.heading ? <Heading>{block.data.heading}</Heading> : null}
          <dl className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-3">
            {block.data.items.map((item, index) => (
              <div key={index} className="flex flex-col gap-1 rounded-tile border border-line p-3">
                <dt className="order-2 text-caption">{item.label || "[what it counts]"}</dt>
                <dd className="order-1 font-display text-2xl font-semibold text-gold-300">
                  {item.value || "[n]"}
                </dd>
                <dd className="order-3 text-xs text-muted">
                  Source: {item.source || "[source]"} · as of{" "}
                  {item.as_of ? formatCalendarDate(item.as_of) : "[date]"}
                </dd>
              </div>
            ))}
          </dl>
          {block.data.note ? <p className="text-caption text-muted">{block.data.note}</p> : null}
        </div>
      );
    case "testimonials":
      return (
        <div className="flex flex-col gap-3">
          <Heading>{block.data.heading || "What our buyers say"}</Heading>
          <Placeholder>
            [Real buyer&apos;s words] · [Name or initials] · [project] · [date]. Shown only when
            approved testimonials with a source and permission exist.
          </Placeholder>
        </div>
      );
    case "offer_banner":
      return (
        <Placeholder>
          {block.data.offer_id
            ? "[The chosen offer while it is live: title, details, end date as plain text, terms link]"
            : `[The live ${block.data.placement ? OFFER_PLACEMENT[block.data.placement].toLowerCase() : ""} offer, if any; nothing otherwise]`}
        </Placeholder>
      );
    case "map":
      return (
        <div className="flex flex-col gap-3">
          {block.data.heading ? <Heading>{block.data.heading}</Heading> : null}
          <Placeholder>
            [Map pin from the project&apos;s Location tab, with its name, address, RERA number and a
            Directions link]
          </Placeholder>
        </div>
      );
    case "steps":
      return (
        <div className="flex flex-col gap-3">
          {block.data.heading ? <Heading>{block.data.heading}</Heading> : null}
          <ol className="flex flex-col gap-2">
            {block.data.items.map((item, index) => (
              <li key={index} className="flex gap-3">
                <span className="font-display text-xl font-semibold text-gold-400">
                  {index + 1}
                </span>
                <span className="flex flex-col">
                  <strong className="text-ivory">{item.title || "[Step title]"}</strong>
                  {item.text ? <span className="text-small">{item.text}</span> : null}
                </span>
              </li>
            ))}
          </ol>
        </div>
      );
    case "columns":
      return (
        <div className="flex flex-col gap-3">
          {block.data.heading ? <Heading>{block.data.heading}</Heading> : null}
          <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-4 text-small">
            {block.data.columns.map((column, index) => (
              <div key={index} className="flex flex-col gap-2">
                {column.heading ? <strong className="text-ivory">{column.heading}</strong> : null}
                <FormattedText
                  text={column.body}
                  empty={<span className="text-muted">[Text]</span>}
                />
              </div>
            ))}
          </div>
        </div>
      );
    case "divider":
      return <hr className="border-gold-line-strong" />;
  }
}

export function BlockPreview({
  block,
  position,
  count,
  size,
}: {
  block: DraftBlock;
  position: number;
  count: number;
  size: "desktop" | "mobile";
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-caption text-muted">
        Preview · <strong className="text-ivory">{BLOCK_TYPES[block.type].name}</strong> · block{" "}
        {position} of {count}
      </p>
      <div
        className={cx(
          "mx-auto w-full overflow-hidden rounded-tile border border-line bg-noir-900",
          size === "mobile" ? "max-w-[390px]" : "",
        )}
      >
        <div
          aria-hidden="true"
          className="flex items-center gap-1.5 border-b border-line px-3 py-2"
        >
          <span className="size-2 rounded-pill bg-noir-700" />
          <span className="size-2 rounded-pill bg-noir-700" />
          <span className="size-2 rounded-pill bg-noir-700" />
          <span className="ml-2 text-xs text-muted">empirebuildcon.com</span>
        </div>
        <div className="p-5">
          <Body block={block} />
        </div>
      </div>
      {!block.is_visible ? (
        <p className="text-caption font-semibold text-danger">
          Hidden: this block is not shown on the website.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Sections of the project page (board NoirProject; task 5.3). Server components; all content is
 * the API's, shown as it is. Empty sections are left out rather than filled with stand-ins.
 *
 * COMPLIANCE:
 *   - Configurations list carpet area first (both units, from the API's display string).
 *   - Construction updates and progress photos carry their dates (D-033 honest labels).
 *   - Payment plans show the stages as entered; no "limited offer" wording (D-035).
 */
import Link from "next/link";
import type { ReactNode } from "react";
import type { components } from "@empire/api-client";
import { FormattedText } from "@empire/ui";
import { PublicImage } from "@/components/media/PublicImage";
import { bhkLabel, distanceLabel, propertyPath } from "@/lib/public/catalogue";
import { ADVANTAGE_KIND, PROPERTY_TYPE, TOWER_KIND } from "@/lib/labels";
import { formatCalendarDate } from "@/lib/dates";
import { AreaText, priceNote, priceText, SoldOutChip } from "./Facts";

type Project = components["schemas"]["PublicProjectDetail"];
type Configuration = components["schemas"]["PublicConfiguration"];
type LinkedMedia = components["schemas"]["PublicLinkedMedia"];

export function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24 flex flex-col gap-5">
      <h2 id={`${id}-title`} className="font-display text-h2-mobile font-semibold sm:text-h2">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function configurationTitle(c: Configuration): string {
  const kind = PROPERTY_TYPE[c.property_type as keyof typeof PROPERTY_TYPE] ?? "";
  return c.name || [bhkLabel(c.bhk), kind.toLowerCase()].filter(Boolean).join(" ");
}

export function ConfigurationsTable({
  projectSlug,
  configurations,
}: {
  projectSlug: string;
  configurations: Configuration[];
}) {
  const rows = [...configurations].sort((a, b) => a.sort_order - b.sort_order);
  return (
    <div className="overflow-x-auto rounded-card border border-line">
      <table className="w-full min-w-[560px] text-left text-small">
        <caption className="sr-only">Home types, carpet area, price and availability</caption>
        <thead className="bg-noir-800">
          <tr>
            {["Home type", "Carpet area", "Price from", "Availability"].map((h) => (
              <th
                key={h}
                scope="col"
                className="px-4 py-3 text-[12px] font-semibold tracking-[0.08em] text-gold-400 uppercase"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} className="border-t border-line" data-testid="configuration-row">
              <th scope="row" className="px-4 py-3 font-semibold text-ivory">
                <Link
                  href={propertyPath(projectSlug, c.slug)}
                  className="inline-flex min-h-11 items-center"
                >
                  {configurationTitle(c)}
                </Link>
              </th>
              <td className="px-4 py-3">
                <AreaText area={c.area} />
              </td>
              <td className="px-4 py-3 font-bold text-gold-300 tabular-nums">
                {priceText(c.price)}
              </td>
              <td className="px-4 py-3">
                {c.sales_status === "sold_out" ? (
                  <SoldOutChip salesStatus="sold_out" />
                ) : (
                  "Available"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-line px-4 py-3 text-caption text-muted">
        Prices: {priceNote(rows[0]?.price ?? { on_request: false, display: "" })}.
      </p>
    </div>
  );
}

export function Gallery({ items, projectName }: { items: LinkedMedia[]; projectName: string }) {
  const photos = items.filter((m) => m.kind === "image");
  if (photos.length === 0) return null;
  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {photos.map((m, i) => (
        <li key={m.id}>
          <figure>
            <PublicImage
              src={m.url}
              alt={m.alt_text || `${projectName}, photo ${i + 1}`}
              label={m.label}
              labelMonth={m.label_month}
              isSample={m.is_sample}
              width={m.width ?? 800}
              height={m.height ?? 600}
              containerClassName="block w-full rounded-tile"
              className="aspect-[4/3] w-full object-cover"
            />
          </figure>
        </li>
      ))}
    </ul>
  );
}

export function Videos({ items, projectName }: { items: LinkedMedia[]; projectName: string }) {
  if (items.length === 0) return null;
  return (
    <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {items.map((v, i) => (
        <li key={v.id} className="flex flex-col gap-2">
          {/* WHY preload="none": the video downloads only when the visitor plays it. */}
          <video
            controls
            preload="none"
            poster={v.thumbnail_url ?? undefined}
            className="aspect-video w-full rounded-tile bg-noir-700"
            aria-label={v.alt_text || `${projectName} video ${i + 1}`}
          >
            <source src={v.url} />
          </video>
          {v.label ? <p className="text-caption text-muted">{labelText(v.label)}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function labelText(label: string): string {
  const map: Record<string, string> = {
    artist_impression: "Artist's impression",
    actual_photo: "Actual footage",
    sample_flat: "Sample flat",
    progress_photo: "Progress footage",
  };
  return map[label] ?? label.replace(/_/g, " ");
}

export function Amenities({ items }: { items: Project["amenities"] }) {
  if (items.length === 0) return null;
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {items.map((a) => (
        <li key={a.id} className="rounded-tile border border-line bg-noir-800 px-4 py-3 text-body">
          {a.name}
        </li>
      ))}
    </ul>
  );
}

export function Specifications({ items }: { items: Project["specifications"] }) {
  if (items.length === 0) return null;
  const groups = new Map<string, string[]>();
  for (const s of [...items].sort((a, b) => a.sort_order - b.sort_order)) {
    groups.set(s.category, [...(groups.get(s.category) ?? []), s.text]);
  }
  return (
    <dl className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {[...groups].map(([category, texts]) => (
        <div key={category} className="rounded-tile border border-line bg-noir-800 p-4">
          <dt className="font-semibold text-ivory">{category}</dt>
          {texts.map((t) => (
            <dd key={t} className="mt-1 text-small text-body">
              {t}
            </dd>
          ))}
        </div>
      ))}
    </dl>
  );
}

export function LocationAdvantages({ items }: { items: Project["location_advantages"] }) {
  if (items.length === 0) return null;
  return (
    <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {[...items]
        .sort((a, b) => a.sort_order - b.sort_order)
        .map((a) => (
          <li key={a.id} className="flex justify-between gap-4 border-b border-line py-2">
            <span className="text-body">
              {a.label}
              <span className="sr-only">
                {" "}
                ({ADVANTAGE_KIND[a.kind as keyof typeof ADVANTAGE_KIND]})
              </span>
            </span>
            <span className="text-muted tabular-nums">
              {distanceLabel(a.distance_km, a.travel_minutes)}
            </span>
          </li>
        ))}
    </ul>
  );
}

export function Progress({ project }: { project: Project }) {
  const towers = [...project.towers]
    .sort((a, b) => a.sort_order - b.sort_order)
    .filter((t) => t.progress_percent !== null && t.progress_percent !== undefined);
  const updates = [...project.construction_updates].sort((a, b) =>
    b.update_date.localeCompare(a.update_date),
  );
  if (towers.length === 0 && updates.length === 0) return null;
  return (
    <div className="flex flex-col gap-6">
      {towers.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {towers.map((t) => (
            <li key={t.id} className="flex flex-col gap-1">
              <div className="flex justify-between text-small">
                <span className="text-body">
                  {TOWER_KIND[t.kind as keyof typeof TOWER_KIND] ?? ""} {t.name}
                </span>
                <span className="font-semibold text-gold-300 tabular-nums">
                  {t.progress_percent}%
                </span>
              </div>
              <div
                role="progressbar"
                aria-label={`${t.name} construction progress`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={t.progress_percent ?? 0}
                className="h-2 overflow-hidden rounded-pill bg-noir-700"
              >
                <div
                  className="h-full rounded-pill bg-gold-500"
                  style={{ width: `${t.progress_percent}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {updates.length > 0 ? (
        <ol className="flex flex-col gap-6">
          {updates.map((u) => (
            <li key={u.id} className="flex flex-col gap-3 border-l border-gold-line pl-4">
              <p className="text-caption font-semibold text-gold-400">
                <time dateTime={u.update_date}>{formatCalendarDate(u.update_date)}</time>
              </p>
              <h3 className="font-semibold text-ivory">{u.title}</h3>
              {u.body ? <FormattedText text={u.body} /> : null}
              {u.photos.length > 0 ? (
                <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {u.photos.map((p) => (
                    <li key={p.id}>
                      <PublicImage
                        src={p.url}
                        alt={p.alt_text || `${u.title} progress photo`}
                        label={p.label || "progress_photo"}
                        labelMonth={p.label_month}
                        isSample={p.is_sample}
                        width={p.width ?? 600}
                        height={p.height ?? 450}
                        sizes="(max-width: 640px) 50vw, 33vw"
                        containerClassName="block w-full rounded-tile"
                        className="aspect-[4/3] w-full object-cover"
                      />
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

export function PaymentPlans({ plans }: { plans: Project["payment_plans"] }) {
  const visible = [...plans]
    .filter((p) => p.is_visible)
    .sort((a, b) => a.sort_order - b.sort_order);
  if (visible.length === 0) return null;
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {visible.map((plan) => (
        <div
          key={plan.id}
          className="flex flex-col gap-3 rounded-card border border-line bg-noir-800 p-5"
        >
          <h3 className="font-semibold text-ivory">{plan.name}</h3>
          {plan.description ? <FormattedText text={plan.description} /> : null}
          {plan.stages.length > 0 ? (
            <table className="w-full text-small">
              <caption className="sr-only">{plan.name} stages</caption>
              <thead>
                <tr>
                  <th
                    scope="col"
                    className="py-1 text-left text-[12px] tracking-[0.08em] text-gold-400 uppercase"
                  >
                    Stage
                  </th>
                  <th
                    scope="col"
                    className="py-1 text-right text-[12px] tracking-[0.08em] text-gold-400 uppercase"
                  >
                    Share
                  </th>
                </tr>
              </thead>
              <tbody>
                {[...plan.stages]
                  .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
                  .map((s, i) => (
                    <tr key={`${s.label}-${i}`} className="border-t border-line">
                      <td className="py-2 text-body">{s.label}</td>
                      <td className="py-2 text-right font-semibold text-gold-300 tabular-nums">
                        {s.percent}%
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function Documents({
  project,
  brochureHref,
}: {
  project: Project;
  brochureHref: string | null;
}) {
  const docs = project.documents;
  if (docs.length === 0 && !brochureHref) return null;
  return (
    <ul className="flex flex-col gap-2">
      {brochureHref ? (
        <li>
          <a
            href={brochureHref}
            className="inline-flex min-h-11 items-center font-semibold"
            data-testid="brochure-link"
          >
            {project.brochure_gated ? "Get the brochure" : "Download brochure (PDF)"}
          </a>
        </li>
      ) : null}
      {docs.map((d, i) => (
        <li key={d.id}>
          <a
            href={d.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center"
          >
            {d.alt_text || `Document ${i + 1}`}
            {d.format ? ` (${d.format.toUpperCase()})` : ""}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export function Faqs({ items }: { items: Project["faqs"] }) {
  const visible = [...items]
    .filter((f) => f.is_visible)
    .sort((a, b) => a.sort_order - b.sort_order);
  if (visible.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      {visible.map((f) => (
        <details key={f.id} className="rounded-tile border border-line bg-noir-800 px-4">
          <summary className="flex min-h-11 cursor-pointer items-center py-3 font-semibold text-ivory">
            {f.question}
          </summary>
          <div className="pb-4">
            <FormattedText text={f.answer} />
          </div>
        </details>
      ))}
    </div>
  );
}

export function formatPossession(iso: string | null | undefined): string | null {
  return iso ? formatCalendarDate(iso) : null;
}

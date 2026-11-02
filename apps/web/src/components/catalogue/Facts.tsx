/**
 * Small display pieces shared by the project and property views (task 5.3): status chips, the
 * price with its note, and the area. The text itself comes from the API's `display` fields
 * (apps/api/src/empire_api/projects/display.py), so the CMS, the site and structured data agree.
 *
 * COMPLIANCE:
 *   - `price.on_request` hides every number: the API already sends "Price on request" as the
 *     display text and no figures; `PriceText` also never reads the min/max/rate fields.
 *   - Every price carries the note "excludes GST, stamp duty and registration" (the API adds
 *     it to `price.note`; the fallback here keeps it if a row has no note).
 *   - Area: carpet first, both units (the API's display string), with the basis in brackets.
 */
import type { components } from "@empire/api-client";
import { Chip } from "@empire/ui";
import { PROJECT_STATUS_LABEL } from "@/lib/public/catalogue";

type Price = components["schemas"]["Price"];
type Area = components["schemas"]["Area"];

export const PRICE_NOTE = "excludes GST, stamp duty and registration";

/** The note shown under a price; always mentions the taxes and charges it leaves out. */
export function priceNote(price: Price): string {
  const note = price.note?.trim();
  if (!note) return PRICE_NOTE;
  return note.toLowerCase().includes("stamp duty") ? note : `${note} (${PRICE_NOTE})`;
}

/** The visible price text: "Price on request" whenever the project asks for that. */
export function priceText(price: Price): string {
  if (price.on_request) return "Price on request";
  return price.display?.trim() || "Price on request";
}

export function PriceText({ price, size = "md" }: { price: Price; size?: "md" | "lg" }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span
        className={`font-extrabold text-gold-300 tabular-nums ${size === "lg" ? "text-[22px]" : "text-lg"}`}
        data-testid="price"
      >
        {priceText(price)}
      </span>
      <span className="text-caption text-muted" data-testid="price-note">
        {priceNote(price)}
      </span>
    </span>
  );
}

export function AreaText({ area }: { area: Area }) {
  if (!area.display) return <span className="text-muted">Area on request</span>;
  return (
    <span className="text-body tabular-nums" data-testid="area">
      {area.display}
    </span>
  );
}

export function ProjectStatusChip({ status }: { status: string }) {
  const label = PROJECT_STATUS_LABEL[status];
  if (!label) return null;
  const variant =
    status === "completed" ? "completed" : status === "ongoing" ? "ongoing" : "upcoming";
  return <Chip variant={variant}>{label}</Chip>;
}

export function SoldOutChip({ salesStatus }: { salesStatus: string }) {
  return salesStatus === "sold_out" ? <Chip variant="soldOut">Sold out</Chip> : null;
}

export function SampleChip({ isSample }: { isSample?: boolean | null }) {
  return isSample ? <Chip variant="sample">SAMPLE</Chip> : null;
}

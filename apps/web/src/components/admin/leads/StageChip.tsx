/**
 * A lead's pipeline stage as a text chip (New, Contacted, Site visit, Negotiation, Booked, Lost),
 * in the stage colours of the CMS boards. Colour is never the only signal: the chip says it.
 */
import { Chip } from "@empire/ui";
import { LEAD_STATUS, LEAD_STATUS_CHIP, type LeadStatus } from "@/lib/leads/labels";

export function StageChip({ status }: { status: LeadStatus }) {
  return (
    <Chip variant={LEAD_STATUS_CHIP[status]} className="whitespace-nowrap">
      {LEAD_STATUS[status]}
    </Chip>
  );
}

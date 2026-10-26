// Display helpers for money, area, phone numbers and India time. Import from "@empire/ui/format"
// (no React needed).
export { formatInr, formatInrFull, formatInrRange } from "./money";
export {
  SQM_PER_SQFT,
  formatArea,
  formatAreaRange,
  sqftToSqm,
  sqftToSqmStored,
  sqmToSqft,
} from "./area";
export { formatPhone, isIndianMobile, maskPhone, telHref, whatsappHref } from "./phone";
export {
  IST_OFFSET_MINUTES,
  addDays,
  formatAge,
  formatClock,
  isCalendarDate,
  istDate,
  istTime,
  istToIso,
  istToday,
  startOfWeek,
  weekdayIndex,
} from "./time";
export {
  MAX_LIST_DEPTH,
  formattedTextToPlain,
  parseFormattedText,
  parseInline,
  type BlockNode,
  type InlineNode,
  type ListItemNode,
} from "./formattedText";

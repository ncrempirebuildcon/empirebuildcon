/**
 * Call and WhatsApp links for a lead, using the full number (boards NoirCmsLead, NoirCmsVisits).
 * Real links (`tel:` and `https://wa.me/`), so they work from a phone with one tap and can be
 * long-pressed or copied. WhatsApp is offered only for mobile numbers; an erased lead has none.
 *
 * COMPLIANCE: only screens that show one lead in full use this (lead detail, the selected site
 * visit); lists show the masked number (SECURITY.md §8).
 */
import { cx, buttonClasses, telHref, whatsappHref } from "@empire/ui";

export interface ContactLinksProps {
  /** The lead's number in E.164, e.g. "+919876543210". */
  phone: string;
  /** The lead's name, added for screen readers ("Call Priya Singh"). */
  name: string;
  /** Icon-only round buttons (the visits side panel) instead of labelled pills. */
  compact?: boolean;
}

const PHONE_ICON =
  "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z";
const CHAT_ICON = "M4 20l1.3-3.9A8 8 0 1 1 8 19.3L4 20z";

function Icon({ d }: { d: string }) {
  return (
    <svg
      aria-hidden="true"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinejoin="round"
    >
      <path d={d} />
    </svg>
  );
}

export function ContactLinks({ phone, name, compact = false }: ContactLinksProps) {
  const tel = telHref(phone);
  const whatsapp = whatsappHref(phone);
  if (!tel) return null;
  // WHY own classes for the round buttons: buttonClasses() carries horizontal padding for a
  // label, which would squeeze a 44 px icon-only circle.
  const round = "inline-flex size-11 items-center justify-center rounded-pill";
  return (
    <span className="flex flex-wrap gap-2">
      <a
        href={tel}
        aria-label={compact ? `Call ${name}` : undefined}
        className={
          compact
            ? cx(round, "border border-gold-500 text-gold-300 hover:bg-gold-tint")
            : buttonClasses("secondary")
        }
      >
        <Icon d={PHONE_ICON} />
        {compact ? null : (
          <span>
            Call<span className="sr-only"> {name}</span>
          </span>
        )}
      </a>
      {whatsapp ? (
        <a
          href={whatsapp}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={compact ? `WhatsApp ${name} (opens WhatsApp)` : undefined}
          className={
            compact
              ? cx(round, "bg-palm-bg text-palm hover:brightness-110")
              : buttonClasses("whatsapp")
          }
        >
          <Icon d={CHAT_ICON} />
          {compact ? null : (
            <span>
              WhatsApp<span className="sr-only"> {name} (opens WhatsApp)</span>
            </span>
          )}
        </a>
      ) : null}
    </span>
  );
}

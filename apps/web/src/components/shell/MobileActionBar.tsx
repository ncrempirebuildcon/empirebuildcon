"use client";
/**
 * Sticky mobile action bar: Call, WhatsApp and Enquire (phones only).
 *
 * Implements DESIGN_SYSTEM & D-038:
 *   - Phones only (hidden on md and above).
 *   - Call and WhatsApp have equal weight.
 *   - Uses company phone & WhatsApp numbers from site settings.
 *   - Replaces `{page}` in WhatsApp template with current path.
 *   - Hidden when numbers are not configured (or placeholders in production).
 */
import { usePathname } from "next/navigation";
import Link from "next/link";
import { buildTelLink, buildWhatsAppLink } from "@/lib/public/format";
import type { PublicSite } from "@/lib/public/api";

export function MobileActionBar({ company }: { company?: PublicSite["company"] }) {
  const pathname = usePathname() || "/";

  const rawPhone = company?.phones?.[0];
  const rawWhatsApp = company?.whatsapp || rawPhone;
  const rawTemplate = company?.whatsapp_message;

  const telHref = buildTelLink(rawPhone);
  const whatsappHref = buildWhatsAppLink(rawWhatsApp, rawTemplate, pathname);

  return (
    <nav
      aria-label="Quick contact"
      className="fixed bottom-0 left-0 right-0 z-40 grid grid-cols-3 gap-2 border-t border-gold-500/40 bg-noir-800/95 px-3 py-2 backdrop-blur-md md:hidden"
      data-testid="mobile-action-bar"
    >
      <a
        href={telHref || "/contact"}
        className="flex min-h-[44px] flex-col items-center justify-center gap-1 text-xs font-bold text-sand-100 hover:text-gold-300"
        aria-label="Call Empire"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#E2B65A"
          strokeWidth="1.7"
          aria-hidden="true"
        >
          <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />
        </svg>
        Call
      </a>

      <a
        href={whatsappHref || "/contact"}
        target={whatsappHref ? "_blank" : undefined}
        rel={whatsappHref ? "noopener noreferrer" : undefined}
        className="flex min-h-[44px] flex-col items-center justify-center gap-1 text-xs font-bold text-palm-300 hover:text-palm-200"
        aria-label="Contact Empire on WhatsApp"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#B6D9A6"
          strokeWidth="1.7"
          aria-hidden="true"
        >
          <path d="M4 20l1.3-3.9A8 8 0 1 1 8 19.3L4 20z" />
        </svg>
        WhatsApp
      </a>

      <Link
        href="/contact#visit"
        className="flex min-h-[44px] items-center justify-center rounded-full bg-gold-500 text-sm font-extrabold text-noir-900 shadow-md hover:bg-gold-400"
      >
        Enquire
      </Link>
    </nav>
  );
}

export default MobileActionBar;

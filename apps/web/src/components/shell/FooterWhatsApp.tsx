"use client";
/**
 * Dynamic WhatsApp contact link for the footer (S8).
 *
 * Uses usePathname() to dynamically substitute `{page}` in the message
 * template with the visitor's current URL path.
 *
 * WHY no aria-label: the visible "WhatsApp us" is the name; a different label fails
 * WCAG 2.5.3 (label in name), which axe reports once a WhatsApp number is set.
 */
import { usePathname } from "next/navigation";
import { buildWhatsAppLink } from "@/lib/public/format";

export function FooterWhatsApp({
  phone,
  template,
  isProduction,
}: {
  phone?: string | null;
  template?: string | null;
  isProduction?: boolean;
}) {
  const pathname = usePathname() || "/";
  const href = buildWhatsAppLink(phone, template, pathname, isProduction);

  if (!href) return null;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex min-h-[44px] items-center gap-1.5 text-palm-300 hover:text-palm-200 font-semibold text-xs"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path d="M4 20l1.3-3.9A8 8 0 1 1 8 19.3L4 20z" />
      </svg>
      WhatsApp us
    </a>
  );
}

export default FooterWhatsApp;

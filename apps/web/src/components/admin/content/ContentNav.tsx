"use client";
/**
 * The "Offers & blog" sub-navigation (board NoirCmsContent's tab row: Offers, Blog posts, FAQs,
 * Testimonials; plus Redirects, which the spec adds here). Each section is its own address, so
 * these are links with `aria-current="page"`, drawn like the editor tabs, not ARIA tabs: a tab
 * list would promise arrow-key switching inside one page.
 *
 * Only sections the role can use are listed (lib/routes.ts `CONTENT_SECTIONS`).
 * SECURITY: hiding a link is a convenience; the API checks the permission on every call.
 */
import Link from "next/link";
import type { ReactNode } from "react";
import { cx } from "@empire/ui";
import { CONTENT_SECTIONS, type ContentSectionId } from "@/lib/routes";
import { useAdminSession } from "@/app/admin/session-context";

export interface ContentNavProps {
  /** The section on screen. */
  current: ContentSectionId;
  /** Optional counts after the labels, e.g. { offers: 5 } ("Offers 5"). */
  counts?: Partial<Record<ContentSectionId, number>>;
}

export function ContentNav({ current, counts }: ContentNavProps) {
  const { can } = useAdminSession();
  const sections = CONTENT_SECTIONS.filter((section) => can(section.permission));
  return (
    <nav aria-label="Offers & blog sections">
      <ul className="flex flex-wrap gap-1 border-b border-line">
        {sections.map((section) => {
          const isCurrent = section.id === current;
          const count = counts?.[section.id];
          return (
            <li key={section.id}>
              <Link
                href={section.href}
                aria-current={isCurrent ? "page" : undefined}
                className={cx(
                  "inline-flex min-h-11 items-center gap-2 px-3.5 text-small font-bold no-underline transition-colors duration-150",
                  isCurrent
                    ? "text-gold-300 shadow-[inset_0_-2px_0_var(--color-gold-500)]"
                    : "text-body hover:text-gold-300",
                )}
              >
                {section.label}
                {count !== undefined ? (
                  <span className="rounded-pill bg-noir-700 px-2 text-xs text-muted tabular-nums">
                    {count}
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/**
 * The top of every "Offers & blog" screen (board NoirCmsContent): the one-line description,
 * an optional main action ("+ New offer"), then the sub-navigation.
 */
export function ContentHeader({
  current,
  description,
  action,
}: {
  current: ContentSectionId;
  description: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[70ch] text-small text-muted">{description}</p>
        {action}
      </div>
      <ContentNav current={current} />
    </div>
  );
}

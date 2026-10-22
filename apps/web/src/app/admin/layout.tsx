/**
 * CMS segment layout. Pages under /admin are never cached (next.config.ts sends no-store) and
 * are client-rendered after a server-side session check (handbook/ARCHITECTURE.md §5).
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: { default: "Empire CMS", template: "%s · Empire CMS" },
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: { children: ReactNode }) {
  return children;
}

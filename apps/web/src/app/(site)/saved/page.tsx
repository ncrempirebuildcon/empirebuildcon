/**
 * /saved: saved homes and projects page (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Requirements:
 *   - Stored in browser localStorage only (no accounts, no cookies).
 *   - Privacy line: "Saved only in this browser."
 *   - Displays no prices, only names and links.
 *   - Verifies if item is still listed via public API; 404 displays "No longer listed" with Remove.
 *   - Empty state links to /projects.
 *   - Metadata through pageMetadata with noindex (D-047).
 *
 * Collaborators: Antigravity <noreply@google.com>, Claude (review 1). Decisions: D-040, D-047, D-049.
 */
import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/catalogue/ListControls";
import { SavedHomesClient } from "@/components/tools/SavedHomesClient";
import { pageMetadata } from "@/lib/public/seo";

export const metadata: Metadata = pageMetadata({
  title: "Saved homes",
  path: "/saved",
  noindex: true,
  fallbackDescriptions: ["Saved only in this browser."],
});

export default function SavedHomesPage() {
  return (
    <article className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8 sm:px-6 lg:px-8">
      <Breadcrumbs
        structuredData={false}
        items={[{ href: "/", label: "Home" }, { label: "Saved homes" }]}
      />

      <header className="flex flex-col gap-2">
        <h1 className="font-display text-[clamp(32px,6vw,56px)] leading-tight font-semibold text-metallic">
          Saved homes
        </h1>
        <p className="text-body text-muted">Saved only in this browser.</p>
      </header>

      <SavedHomesClient />
    </article>
  );
}

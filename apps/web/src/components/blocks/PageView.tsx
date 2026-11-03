/**
 * One page-builder page on the public site (task 5.5a, D-045): its title (as the h1 unless a
 * leading hero block carries it), the DRAFT notice and version for legal pages, then its blocks.
 *
 * COMPLIANCE (D-017): a legal page whose text is still marked draft shows a visible notice, so
 * nobody takes unapproved wording for the final terms. Production refuses to publish such a
 * page (Phase 4), so in practice the notice is seen in development and staging.
 */
import type { components } from "@empire/api-client";
import { BlockList, startsWithHero } from "./Blocks";

type PublicPage = components["schemas"]["PublicPage"];

export function PageView({ page, path }: { page: PublicPage; path: string }) {
  const heroTitle = startsWithHero(page.blocks);
  // Readers must know which version of the terms they read: under the title, or under the hero.
  const version =
    page.kind === "legal" && page.legal_version ? (
      <p className="text-caption text-muted" data-testid="legal-version">
        Version {page.legal_version}
      </p>
    ) : null;
  return (
    <article className="mx-auto flex max-w-7xl flex-col gap-10 px-4 py-10 sm:px-6 lg:px-8">
      {page.kind === "legal" && page.is_draft_text ? (
        <p
          role="note"
          className="rounded-tile border border-danger bg-danger-bg p-4 text-small text-danger-on-bg"
          data-testid="legal-draft-notice"
        >
          <strong>DRAFT.</strong> This text is a draft awaiting Empire&apos;s approval. It is not
          yet in force.
        </p>
      ) : null}
      {heroTitle ? null : (
        <header className="flex flex-col gap-2">
          <h1 className="font-display text-[clamp(32px,6vw,58px)] leading-tight font-semibold text-balance text-metallic">
            {page.title}
          </h1>
          {version}
        </header>
      )}
      <BlockList blocks={page.blocks} path={path} afterFirst={heroTitle ? version : null} />
    </article>
  );
}

export default PageView;

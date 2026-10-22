/**
 * Renders structured data (JSON-LD) for search engines (handbook/ARCHITECTURE.md §16).
 *
 * SECURITY: this is the only place allowed to use dangerouslySetInnerHTML (SECURITY.md §5).
 * The JSON is serialised and every "<" is escaped as <, so a value containing
 * "</script>" can't close the tag and inject markup. Do not pass pre-built strings here.
 */
export function JsonLd({ data }: { data: Record<string, unknown> }) {
  const json = JSON.stringify(data).replace(/</g, "\\u003c");
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />;
}

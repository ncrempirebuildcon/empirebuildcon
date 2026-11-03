/**
 * Renders one structured data (JSON-LD) block for search engines (handbook/ARCHITECTURE.md §16;
 * task 5.6, D-047).
 *
 * SECURITY: this is the only place allowed to use dangerouslySetInnerHTML (SECURITY.md §5,
 * eslint.config.mjs). The data is serialised by `ldJson`, which escapes every "<" (and the line
 * separators), so a value containing "</script>" can't close the tag and inject markup. Do not
 * pass pre-built strings here. The script carries the request's CSP nonce (proxy.ts, x-nonce).
 */
import { headers } from "next/headers";
import { ldJson } from "@/lib/public/seo";

type Ld = Record<string, unknown>;

export async function JsonLd({ data }: { data: Ld | Ld[] | null | undefined }) {
  if (!data || (Array.isArray(data) && data.length === 0)) return null;
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <script
      type="application/ld+json"
      nonce={nonce}
      dangerouslySetInnerHTML={{ __html: ldJson(data) }}
    />
  );
}

export default JsonLd;

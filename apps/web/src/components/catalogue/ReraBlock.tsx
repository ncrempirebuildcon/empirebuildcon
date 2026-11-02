/**
 * UP-RERA badge: QR code on an ivory tile, registration number(s) and "Verify on up-rera.in"
 * (DESIGN_SYSTEM §8 "RERA badge"; task 5.3).
 *
 * COMPLIANCE (AGENTS.md "Honest content", D-002): every project and property view shows the
 * RERA number, the QR code and the regulator's website. A published project always has all
 * three (the CMS blocks publishing without them), so this component never hides itself. If the
 * API ever sends no QR or number, the badge still renders the authority and the portal link, so
 * the visitor can look the project up.
 *
 * Towers or phases with their own registration number are listed under the project's number.
 */
import type { components } from "@empire/api-client";
import { PublicImage } from "@/components/media/PublicImage";

type Rera = components["schemas"]["PublicRera"];
type Tower = components["schemas"]["Tower"];

const DEFAULT_PORTAL = "https://www.up-rera.in";

/** The host shown to the visitor ("up-rera.in"), from the stored portal URL. */
export function portalHost(url: string | null | undefined): string {
  try {
    return new URL(url || DEFAULT_PORTAL).hostname.replace(/^www\./, "");
  } catch {
    return "up-rera.in";
  }
}

/** Tower or phase numbers that differ from the project's own number, in display order. */
export function towerNumbers(rera: Rera, towers: Tower[] = []): { name: string; number: string }[] {
  return [...towers]
    .sort((a, b) => a.sort_order - b.sort_order)
    .filter((t) => t.rera_number && t.rera_number !== rera.number)
    .map((t) => ({ name: t.name, number: t.rera_number as string }));
}

export function ReraBlock({
  rera,
  towers = [],
  projectName,
  variant = "panel",
}: {
  rera: Rera;
  towers?: Tower[];
  projectName: string;
  /** `panel`: QR tile and text (project and property pages). `line`: one line (cards). */
  variant?: "panel" | "line";
}) {
  const portal = rera.url || DEFAULT_PORTAL;
  const host = portalHost(portal);
  const extra = towerNumbers(rera, towers);

  if (variant === "line") {
    return (
      <p className="text-small text-muted" data-testid="rera-line">
        <span className="font-semibold text-body">{rera.authority}</span>{" "}
        <span className="tabular-nums">{rera.number ?? "number on the project page"}</span> ·{" "}
        <a
          href={portal}
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-2"
          aria-label={`Verify ${projectName} on ${host} (opens in a new tab)`}
        >
          Verify
        </a>
      </p>
    );
  }

  return (
    <div
      className="flex flex-col gap-4 rounded-card border border-gold-line bg-noir-800 p-5 sm:flex-row sm:items-center"
      data-testid="rera-block"
    >
      {rera.qr ? (
        <div className="shrink-0 self-start rounded-tile bg-ivory-tile p-2">
          <PublicImage
            src={rera.qr.url}
            alt={`${rera.authority} QR code for ${projectName}`}
            width={112}
            height={112}
            sizes="112px"
            showBadge={false}
            className="h-28 w-28 object-contain"
          />
        </div>
      ) : null}
      <div className="flex flex-col gap-1.5">
        <p className="font-display text-eyebrow tracking-[0.28em] text-gold-400 uppercase">
          {rera.authority} registration
        </p>
        {rera.number ? (
          <p className="text-lg font-bold text-ivory tabular-nums" data-testid="rera-number">
            {rera.number}
          </p>
        ) : null}
        {extra.length > 0 ? (
          <ul className="text-small text-body">
            {extra.map((t) => (
              <li key={t.number}>
                {t.name}: <span className="tabular-nums">{t.number}</span>
              </li>
            ))}
          </ul>
        ) : null}
        <a
          href={portal}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center font-semibold underline underline-offset-4"
        >
          Verify on {host}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      </div>
    </div>
  );
}

export default ReraBlock;

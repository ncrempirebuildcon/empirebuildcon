# @empire/ui

Black & gold design system for the Empire website and CMS: generated design tokens, a few accessible React components, and money/area display helpers.

| Path | What |
|---|---|
| `src/theme.css` | **Generated** Tailwind v4 `@theme` from `brand/tokens/empire-noir.json`. Never edit by hand. |
| `src/tokens.ts` | **Generated** typed copy of the same tokens |
| `src/components/` | `Button`, `TextField`, `Checkbox`, `Chip`, `Alert` |
| `src/format/` | `formatInr`, `formatInrRange`, `formatInrFull`, `sqftToSqm`, `formatArea`, `formatAreaRange` |

## Commands

```bash
pnpm --filter @empire/ui tokens        # regenerate theme.css + tokens.ts after changing the JSON
pnpm --filter @empire/ui tokens:check  # CI: fails if the generated files are stale
pnpm --filter @empire/ui test          # unit tests (Vitest + Testing Library)
pnpm --filter @empire/ui lint
pnpm --filter @empire/ui typecheck
```

## Rules

- **Tokens only.** Use the Tailwind classes generated from the tokens (`bg-noir-900`, `text-gold-300`, `rounded-card`, `font-display`). Never hard-code a colour or radius that has a token (handbook/CODE_STYLE.md §3).
- **No facts in components.** Prices, RERA numbers and counts come from the CMS through props.
- **Accessibility (WCAG 2.1 AA):** visible labels, `aria-describedby` for hints and errors, 44 px touch targets, a visible focus ring, and text on every status chip. Consent checkboxes are never pre-ticked (`COMPLIANCE`).
- Apps consume this package as TypeScript source (`transpilePackages` in Next.js) and must add `@source` for `packages/ui/src` in their Tailwind CSS so the component classes are generated.

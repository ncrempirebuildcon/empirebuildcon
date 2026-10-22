# @empire/web

The Empire public website and the CMS user interface (Next.js 16 App Router, TypeScript, Tailwind CSS 4).

## What is here (Phase 3)

| Route | What |
|---|---|
| `/` | Black & gold "coming soon" holding page (`noindex`) |
| `/admin/login` | Staff sign-in (email + password; generic error; lockout message) |
| `/admin` | CMS shell after a server-side session check: menu by role, signed-in user, sign-out |
| 404 / error | Black & gold not-found page and a "Try again" error state |
| `/robots.txt` | Disallows everything until go-live (`TODO(phase-9)`) |

The public pages arrive in Phase 5 and the CMS screens in Phase 4. Designs are on the design canvas; see `handbook/README.md#designs`.

## How it fits together

- The browser only calls `/api/*` on this site; `next.config.ts` rewrites those calls to `API_ORIGIN` (handbook/ARCHITECTURE.md §3). `skipTrailingSlashRedirect` stays on (`DO NOT CHANGE`).
- Security headers are set in `next.config.ts` (handbook/SECURITY.md §4). The nonce-based CSP comes in Phase 5.
- CMS pages check the session on the server (`src/lib/session.ts`) and are never cached.
- Styling uses only the generated tokens from `@empire/ui` (`bg-noir-900`, `text-gold-300`, `rounded-card`, `font-display`…). Fonts are self-hosted from npm (`@fontsource`).

## Commands

```bash
pnpm --filter @empire/web dev        # http://localhost:3000 (start the API on :8000 too)
pnpm --filter @empire/web build
pnpm --filter @empire/web start
pnpm --filter @empire/web lint
pnpm --filter @empire/web typecheck
```

Environment (see `.env.example` at the repo root): `API_ORIGIN`, `SITE_URL`.

## Rules

- **Tokens only:** never hard-code a colour, radius or font that has a token.
- **No facts in code:** prices, RERA numbers, counts and company details come from the API/CMS. Unknown facts are `[placeholders]`.
- **Accessibility (WCAG 2.1 AA):** real buttons and links, a visible label on every field, a focus ring, 44 px touch targets, and text on every status.
- `dangerouslySetInnerHTML` is banned by lint except in `src/components/JsonLd.tsx` (`SECURITY`).

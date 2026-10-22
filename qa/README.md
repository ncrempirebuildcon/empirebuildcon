# @empire/qa

Browser journeys, accessibility checks and performance budgets (handbook/ARCHITECTURE.md §21).

| File | What it checks |
|---|---|
| `specs/smoke.spec.ts` | Home page, 404, security headers, `/api/*` proxy, no redirect on a trailing slash |
| `specs/a11y.spec.ts` | axe (WCAG 2.1 A/AA): no serious or critical issues on home, staff sign-in, 404 |
| `specs/login.spec.ts` | Sign-in with the generic error, redirect when signed out, cookie flags, no browser storage, sign-out |
| `lighthouserc.json` | Lighthouse (mobile) on `/`: performance, accessibility and best practices ≥ 0.9 |

## Run locally

```bash
# once: PostgreSQL running (docker compose up -d db) and dependencies installed (pnpm install, uv sync)
pnpm --filter @empire/web build      # Playwright starts the built app with `next start`
pnpm e2e                             # from the repo root; starts the API and web app if not running
pnpm --filter @empire/qa lhci        # Lighthouse budgets
```

- `global-setup.ts` runs the database migrations and creates a throwaway super-admin (random email and password) with the API's dev/test-only `empire-api create-user`. The credentials go to `qa/.auth/` (git-ignored).
- API secrets for the run are generated on the spot unless the environment provides them. You need no real secrets to run the suite.
- On a machine with a pre-installed Chromium, set `PW_CHROMIUM_PATH` to it; otherwise run `pnpm --filter @empire/qa exec playwright install chromium` once.

## Exceptions

- **SEO score:** only a warning until go-live. The whole site sends `noindex` and `robots.txt` disallows crawling until the Phase 9 gate, which Lighthouse marks as an SEO failure on purpose. It becomes an error at go-live (`TODO(phase-9)` in `apps/web/src/app/robots.ts`).

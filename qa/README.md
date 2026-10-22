# @empire/qa

Browser journeys, accessibility checks and performance budgets (handbook/ARCHITECTURE.md §21).

| File | What it checks |
|---|---|
| `specs/smoke.spec.ts` | Home page, 404, security headers, `/api/*` proxy, no redirect on a trailing slash |
| `specs/a11y.spec.ts` | axe (WCAG 2.1 A/AA): no serious or critical issues on home, staff sign-in, 404 |
| `specs/login.spec.ts` | Sign-in with the generic error, redirect when signed out, cookie flags, no browser storage, sign-out |
| `specs/projects.spec.ts` | CMS journey: add a city and locality in the catalogue, create a project, see the publish blockers (and the API's 409), set locality, a plus code pasted with a place name, RERA number and price (Duplicate waits while unsaved), add a configuration with area and price, add and reorder towers (and the "Discard your changes?" question), archive, SAMPLE badge and banner |
| `specs/a11y-cms.spec.ts` | axe on `/admin/projects`, `/admin/projects/new`, every tab of `/admin/projects/[id]`, a confirm dialog, and `/admin/catalogue`; also deletes a never-published draft |
| `specs/responsive-cms.spec.ts` | Phone width (390 × 844): no sideways page scroll on `/admin/projects`, every editor tab, and `/admin/catalogue` (wide tables scroll inside their own region) |
| `specs/auth.setup.ts` | The "setup" project: signs the throwaway super-admin in once and saves the session (`qa/.auth/cms-state.json`) for the CMS specs |
| `lib/auth.ts` | `CMS_STATE`, `signIn()`, `apiCall()` (API as the signed-in user, with the CSRF token), `seriousA11yViolations()`, `runId()` |
| `lighthouserc.json` | Lighthouse (mobile) on `/`: performance, accessibility and best practices ≥ 0.9 |

## Run locally

```bash
# once: PostgreSQL running (docker compose up -d db) and dependencies installed (pnpm install, uv sync)
pnpm --filter @empire/web build      # Playwright starts the built app with `next start`
pnpm e2e                             # from the repo root; starts the API and web app if not running
pnpm --filter @empire/qa lhci        # Lighthouse budgets
```

- `global-setup.ts` runs the database migrations, loads the default amenity catalogue and the SAMPLE projects (`empire-api seed --sample`, idempotent, refused in production) and creates a throwaway super-admin (random email and password) with the API's dev/test-only `empire-api create-user`. The credentials go to `qa/.auth/` (git-ignored).
- **Sign-in limit:** the API allows 10 sign-in attempts per network per 15 minutes (SECURITY.md §1), successful ones included. A run signs in three times (the setup project and two in `login.spec.ts`), so locally you can run the suite about three times in a quarter of an hour; after that, wait for the next 15-minute window.
- Journeys create their own cities, localities and projects with a unique run id in the name, so runs never clash on slugs in the shared `empire_dev` database.
- API secrets for the run are generated on the spot unless the environment provides them. You need no real secrets to run the suite.
- On a machine with a pre-installed Chromium, set `PW_CHROMIUM_PATH` to it; otherwise run `pnpm --filter @empire/qa exec playwright install chromium` once.

## Exceptions

- **SEO score:** only a warning until go-live. The whole site sends `noindex` and `robots.txt` disallows crawling until the Phase 9 gate, which Lighthouse marks as an SEO failure on purpose. It becomes an error at go-live (`TODO(phase-9)` in `apps/web/src/app/robots.ts`).

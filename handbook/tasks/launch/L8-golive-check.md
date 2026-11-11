# L8 · Go-live check

| | |
|---|---|
| **Task id** | `L8` |
| **Track** | A (Claude) |
| **Branch** | `feat/l8-golive-check` |
| **Depends on** | — |
| **Status** | Built 11 Nov 2026 |
| **Decision** | none (RUNBOOK §3–§4, D-002, D-015, D-017, D-034, D-050) |

## Goal

Before go-live, one command says whether the database is ready to be the live site, and one says whether the deployed website looks right from outside. Nothing is missed on the day, and the content team can run the database report while entering content (L5) to see what is left.

## Scope

1. **`empire-api golive-check`** (`apps/api/src/empire_api/golive.py`):
   - Read-only. One PASS, WARN or FAIL line per check; exit code 1 on any FAIL; `--json` for a file.
   - Content is judged through the public API's own builders, so "live" means exactly what the website shows.
   - **Checks:**
     - `APP_ENV` and an https `SITE_URL`;
     - at least one live project, and no live project with a publish blocker (RERA number, QR, configuration; D-002);
     - every legal page published and not a draft (D-017);
     - the consent texts every form needs published and approved: `lead_form`, `marketing` and `brochure`, plus `cookies` with tracking IDs and `chat` with the chat flag (D-034);
     - contact details (phone, email, address, WhatsApp) set;
     - no sample data shown (D-015);
     - no "[placeholder]" text on a live project, page or post, or in the contact details;
     - an active super-admin with two-factor sign-in; admins without it listed (WARN);
     - the shared sales inbox for lead alerts (D-050, WARN);
     - `chat_widget` off, or on with a provider;
     - no background event waiting over 45 minutes (the Scheduler job), and no event failed for good in 7 days (WARN).
2. **`pnpm --filter @empire/qa golive -- <url>`** (`qa/scripts/golive-check.ts`):
   - GET requests only.
   - **Checks:**
     - the home page and its security headers (CSP enforced or report-only, nosniff, referrer policy, and HSTS with `--production`);
     - robots.txt: blocked on staging, allowed with `--production`, with the sitemap line;
     - the sitemap's addresses all on the site's host;
     - a project page from the sitemap showing UP-RERA and up-rera.in;
     - `/api/health/live` through the site;
     - the http → https redirect;
     - each `--alias` redirecting permanently;
     - with `--api-origin`, the API refusing calls without the edge key (D-027).
3. RUNBOOK §3 and §4 use both.

**Out of scope:** changing any content or setting; checks that need an account (Search Console, UptimeRobot).

## Tests

- `tests/test_golive.py`:
  - the placeholder rule;
  - each check's FAIL and PASS (projects, a lost RERA QR, legal pages, a page placeholder, consent, two-factor, the chat flag, stuck and dead events);
  - the command's exit code and JSON.
- **Failure proofs:**
  - without the blocker check, the lost-QR test fails;
  - without the placeholder scan, 5 tests fail.
- The site script was run against the local production build.

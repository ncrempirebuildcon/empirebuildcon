# L1 · Steady tests and small fixes (Track B)

| | |
|---|---|
| **Task id** | `L1` |
| **Track** | B (developer agent), D-040 |
| **Branch** | `fix/l1-steady-tests` |
| **Depends on** | `main` at or after `9e26435` (5.6b merged) |
| **Status** | Ready |

## Goal

The full e2e run (`pnpm --filter @empire/qa e2e`) passes twice in a row on a 2-CPU machine, with no test retried into passing and no timeout simply raised. Also two small leftovers from the 5.7b and 5.6b reviews.

## What has been seen (Claude's runs, 4–6 Nov 2026)

Under the full run, admin tests fail now and then. Each passes when its spec runs alone (checked twice for each).

| Test | What failed |
|---|---|
| `leads.spec.ts:276` "typed work … asks before it is thrown away" | the "Leave without saving?" dialog not visible within 5 s (failed in 3 of 6 full runs) |
| `leads.spec.ts:35` site-visit request to dashboard | a locator not visible at line ~147 |
| `content.spec.ts:387` library photo for a hero block | "Clicking the checkbox did not change its state" on the photo radio |
| `a11y-content.spec.ts` | the "Pages" table not found |
| `a11y-cms.spec.ts:185` media library | the "Media files" list not found |

In the same runs the web server's log shows **`Failed to proxy http://localhost:8000/… Error: socket hang up`** for admin API calls (cities, projects, media files). So the API sometimes drops requests under load, and the screen then shows no list. That is the likeliest common cause, and it is the first thing to prove or rule out.

## Read first

- `AGENTS.md`, `handbook/agents/WORKFLOW.md`, `qa/README.md`.
- `qa/playwright.config.ts`: how the API (one uvicorn process) and the web app are started, workers and projects.
- `apps/web/src/proxy.ts` and `apps/web/src/lib/edge.ts`: how `/api/*` is proxied to the API (read only).
- `apps/api/src/empire_api/db.py` (pool size) and `config.py`.

## Scope

1. **Find the cause of "socket hang up".** Run the full suite with timing logs (uvicorn access log with durations, the DB pool's checkout wait, the API's own logs). Reproduce it and name the cause with evidence, for example:
   - the DB pool is exhausted and requests wait past the proxy's timeout;
   - uvicorn's keep-alive closes connections the proxy reuses;
   - a slow endpoint holds the single worker.
2. **Fix the cause where it lives.** If the fix belongs to test setup (the test server's uvicorn flags, workers, pool size via env in `playwright.config.ts`), change it there. If it is a real API or proxy bug that could also hit production, **stop and describe it in your report**. Claude fixes those (Track A owns `apps/api` and `proxy.ts`).
3. **Each listed test:** after the fix, if one still fails, find its own cause (a race in the test or in the screen) and fix it. Use Playwright's waiting assertions, not `waitForTimeout`; no `retries`, no larger timeouts as the fix.
4. **/saved message** (5.7b review 3 follow-up): when removing a saved home fails, the message must say "Couldn't update saved homes in this browser", not "Couldn't save in this browser". Add a unit test.
5. **`.env.example`** (5.6b review): align the `ALLOW_INDEXING` comment with the lines around it.

**Out of scope:** new features; changes to `apps/api` or `proxy.ts` (report them instead); the Lighthouse job.

## Tests required

- Two full e2e runs, both green, pasted (counts and time).
- For each test you changed: show it failing before your change, under the same load. Paste the real output.
- The /saved unit test fails without the fix.

## Acceptance list

- [ ] The cause of "socket hang up" is named, with evidence (log lines, numbers).
- [ ] Fixed where it lives, or reported for Claude if it is in `apps/api` or `proxy.ts`.
- [ ] Every listed test is steady; nothing fixed by retries, sleeps or bigger timeouts.
- [ ] Two full e2e runs green in a row.
- [ ] /saved remove message and unit test.
- [ ] `.env.example` comment aligned.
- [ ] `qa/README.md` updated if how tests run changed; D-051 proposed in the report if so.

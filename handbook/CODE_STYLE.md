# Code style and comments

The goal: someone new, human or AI, can open any file and understand **what it does, why it is that way, and what must not be changed**, without asking the person who wrote it.

## 1. General

- **Language:** code, comments, commit messages and handbook pages are in simple English. Visitor-facing copy lives in the CMS or in message files, not hard-coded.
- **Formatting is automatic:** Prettier for TypeScript, CSS, JSON and Markdown; Ruff format for Python. Don't argue style in reviews; the formatter decides. `.editorconfig` sets UTF-8, LF line endings and 2-space indents (4 for Python).
- **Small units:** aim for functions under about 40 lines and files under about 400 lines. Split larger ones by responsibility.
- **Names say what something is:** `priceMinInr`, `carpetAreaSqft`, `isSample`, `leadConsentTextVersion`. Use no abbreviations except the domain ones (BHK, RERA, UTM, OTP). Units go in the name (`…Inr`, `…Sqft`, `…Ms`).
- **One source of truth:**
  - Money and area formatting use the shared helpers (`formatInr`, `sqftToSqm`), never ad-hoc maths.
  - Colours and radii come from the tokens.
  - Permissions come from the permission matrix.
- **Errors:**
  - Never swallow an error. Either handle it, or log it with context (structlog / Sentry) and re-raise.
  - API errors use the problem+json shape from the OpenAPI spec.
- **Logs:** never log personal data (names, phone numbers, emails) or secrets. Log IDs instead.

## 2. Comments

Comments explain **why**, not what; the code already says what. A wrong comment is a bug, so update or delete comments when you change the code.

### 2.1 File header (every non-trivial module)

Each module starts with a short header:
- what the file is for;
- its main collaborators;
- the decisions it implements;
- anything that must not change.

```python
"""Lead intake: validates a public enquiry, records consent, and emits lead.created.

Collaborators: consent.py (text versions), outbox.py (events), rate_limit.py.
Implements: D-016 (routing), D-017 (consent wording), ARCHITECTURE §8.

DO NOT CHANGE: consent is stored in the same transaction as the lead. Splitting
them would allow a lead without a consent record, which breaks DPDP compliance.
"""
```

```ts
/**
 * RERA badge: registration number + QR (on an ivory tile) + link to up-rera.in.
 * Used on every project, property and campaign view (D-002, DESIGN_SYSTEM §8).
 *
 * COMPLIANCE: do not hide this behind a tab or accordion, and do not shrink the
 * QR below 96 px. UP-RERA rules require it to be visible and scannable.
 */
```

### 2.2 Tags (always uppercase and followed by a colon, so they can be searched)

| Tag | Use it when | Changing the tagged code needs |
|---|---|---|
| `WHY:` | The code looks odd or there was a simpler-looking option you rejected | Normal review |
| `INVARIANT:` | A rule that must always hold, e.g. "a lead always has a consent row" | Normal review plus a test proving the rule still holds |
| `DO NOT CHANGE:` | Changing it breaks something that isn't obvious. Say **what breaks** and **where the reason is written** (decision, issue, law) | **Owner approval** ([CONTRIBUTING §7](CONTRIBUTING.md#owner-approval)) |
| `COMPLIANCE:` | Required by law or regulation (UP-RERA display, DPDP consent and erasure, ad rules) | **Owner approval** |
| `SECURITY:` | Auth, permissions, upload checks, rate limits, secrets, headers | Review by a second person who reads SECURITY.md |
| `PERF:` | Written this way for speed or cost (e.g. Neon sleeping, Cloud Run cold starts) | Normal review plus before/after numbers |
| `TODO(phase-N):` or `TODO(@name):` | Planned work. It must have an owner or a phase, and say what is missing | — |
| `WORKAROUND:` | Working around a bug in a library or service. Link the upstream issue and say when to remove it | Normal review |

Don't use bare `TODO`, `FIXME` or `XXX`. CI will flag them.

### 2.3 Complex logic

When a function does several steps, or anything with money, dates, permissions, consent or retries, give it a **"How it works"** block and number the steps in the code:

```python
def deliver_outbox_batch(session, now):
    """Deliver due outbox events to their handlers and webhooks.

    How it works:
      1. Lock up to 50 due rows with FOR UPDATE SKIP LOCKED, so two workers
         never take the same event.
      2. Call each handler; on success mark the row delivered.
      3. On failure, schedule a retry with exponential backoff (max 8 tries),
         then mark it dead and alert (ARCHITECTURE §9).

    INVARIANT: an event is delivered at least once; handlers must be idempotent.
    PERF: runs every 15 minutes from Cloud Scheduler (D-007), not as a loop,
    so the database can sleep between runs on the free tier.
    """
    rows = lock_due_events(session, now, limit=50)  # 1
    for row in rows:
        try:
            dispatch(row)  # 2
            mark_delivered(row, now)
        except Exception as exc:  # noqa: BLE001 — every failure must be retried, see step 3
            schedule_retry_or_dead(row, exc, now)  # 3
```

```ts
// WHY: area is stored once, in square metres (ARCHITECTURE §6); every other unit
// shown on screen is derived from it, so two figures can never disagree.
export const sqmToSqft = (sqm: number) => Math.round(sqm / 0.092903);
```

### 2.4 Docstrings

- **Python:** Google-style docstrings on public functions and classes, with Args, Returns and Raises where they help.
- **TypeScript:** TSDoc on exported functions, hooks and component props. Say what each prop does and whether it is required.
- **SQL and Alembic migrations:** a header comment saying what changes, why, and whether the downgrade is safe.

## 3. TypeScript / Next.js (apps/web, packages/*)

- Use `strict` TypeScript. Avoid `any`; if you must, add a `WHY:`.
- Server Components by default. Add `"use client"` only for interaction, and say why in one line.
- **Data:** call the API only through the generated client in `packages/api-client`. Validate forms with Zod.
- **Styling:** Tailwind classes mapped to the tokens. Never hard-code a hex colour that has a token.
- **Accessibility:** use real `<button>` and `<a>` elements, a `<label>` for every input, `aria-*` on toggles, a visible focus ring and 44 px touch targets ([DESIGN_SYSTEM §9](DESIGN_SYSTEM.md)).
- **Content:** no visitor-facing text that claims facts (prices, RERA numbers, counts) in code. It comes from the CMS.

## 4. Python / FastAPI (apps/api, apps/worker)

- Type hints everywhere; mypy runs in CI.
- Layout per module: `routes.py` (HTTP only), `service.py` (business rules), `models.py` (SQLAlchemy), `schemas.py` (Pydantic).
- Other modules call your **service functions**, never your tables ([ARCHITECTURE §2](ARCHITECTURE.md)).
- **Permissions:** every route declares its permission (`require("leads.read")`). A route without one fails a test.
- **Time:** store UTC and show Asia/Kolkata. Use `datetime.now(UTC)`, never naive datetimes.
- **Money:** whole rupees as integers. Never use floats for money.

## 5. Tests

- Every bug fix comes with a test that fails without the fix.
- Every endpoint has API tests for success, validation errors and permission denied.
- Every `INVARIANT:` has a test that names it.
- Browser journeys (Playwright) cover the lead form, CMS sign-in, project edit → publish → visible on the site, and media upload ([ARCHITECTURE §21](ARCHITECTURE.md)).

## 6. Feature flags

- Risky or unfinished features ship behind a flag that is off by default. Use snake_case names, list them in ARCHITECTURE and DECISIONS, and show them in CMS Settings.
- When a flag has been on in production for a month, remove the flag and the dead code in a follow-up PR.

## 7. Honest data in code and seeds

- Seed and sample data set `is_sample = true` and uses the `SAMPLE` naming from the design boards. The production build refuses to publish sample rows.
- Never put real-looking invented facts in fixtures shown to visitors: no fake testimonials, awards or counts. Use `[placeholders]`.

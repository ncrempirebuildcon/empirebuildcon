# empire-api

The Empire API (FastAPI), its background worker and the `empire-api` admin CLI. One Python package, `empire_api`, with two entry points (D-010).

Read [`../../handbook/README.md`](../../handbook/README.md) first. The rules for code and comments are in [`CODE_STYLE.md`](../../handbook/CODE_STYLE.md); the design is in [`ARCHITECTURE.md`](../../handbook/ARCHITECTURE.md) and [`SECURITY.md`](../../handbook/SECURITY.md).

## Layout

```
apps/api/
├─ pyproject.toml          pinned dependencies (D-006), ruff/mypy/pytest settings
├─ uv.lock                 exact versions; commit it
├─ alembic.ini, migrations/   database migrations (0001_foundation = Phase 3 tables,
│                          0002_catalogue = projects, their children, cities, localities, amenities,
│                          0003_media = media library, upload intents, media links,
│                          0004_leads = consent texts, leads, consent records, notes, timeline,
│                          site visits, 0005_content = pages, blocks, posts, FAQs, offers,
│                          testimonials, redirects, 0006_settings_auth = two-factor, sign-in
│                          challenges, the sent-mail log, consent_text.published_by)
├─ scripts/                make_common_passwords.py (regenerates the weak-password list)
├─ src/empire_api/
│  ├─ main.py              create_app(): routers, middleware, error handlers, OpenAPI tweaks
│  ├─ config.py            Settings from env vars; refuses unsafe secrets in staging/production
│  ├─ db.py                engine, sessions, declarative Base (UUID v7, timestamptz)
│  ├─ errors.py            RFC 9457 problem+json for every error
│  ├─ logs.py              structured JSON logs, phone masking
│  ├─ health.py            /api/health/live (no DB) and /api/health (DB check)
│  ├─ middleware/          trailing-slash strip (no redirects), request id, security headers
│  ├─ platform/            audit log, outbox writer, PostgreSQL rate limits, crypto helpers
│  ├─ users/               sign-in, sessions, CSRF, passwords, roles matrix, staff admin
│  │  ├─ sign_in.py        the password step and the two-factor step or forced set-up after it
│  │  ├─ lockout.py        D-027 counting (passwords AND codes, per account and network)
│  │  ├─ totp.py           our own RFC 6238 codes; two_factor.py = set-up, proofs, recovery
│  │  │                    codes, reset; my_account.py = the signed-in two-factor operations;
│  │  │                    qr.py = the set-up QR (segno); two_factor_cookie.py = __Host-empire_2fa
│  │  ├─ routes_auth.py, routes_two_factor.py, routes_admin.py   HTTP only
│  │  ├─ audit_log.py      the audit-log reader (filters, IST days, masked IPs); present.py
│  │  ├─ role_docs.py      plain-English wording for the role table (roles.py is the matrix)
│  │  └─ seed.py           four "Sample …" accounts for `seed --sample` (dev/test, invited only)
│  ├─ site_settings/       settings groups and feature flags (Phase 4 part 5)
│  │  ├─ groups.py         one strict model per group and who may change it; fields.py = GSTIN,
│  │  │                    phones, social hosts, tracking ids, sender name
│  │  ├─ service.py        read typed, update one group (permission, checks, audit, event)
│  │  ├─ flags.py          flags, their titles and the one switching rule (admin_2fa)
│  │  └─ routes.py         /admin/settings, /admin/settings/{group}, /admin/flags
│  ├─ mail/                email (Phase 4 part 5, D-007): transport.py (interface), resend.py
│  │  │                    (httpx, no SDK), dev.py (dev mailbox, never sends), templates.py,
│  │  │                    brand.py (company lines from Settings), delivery.py (once per
│  │  │                    recipient), handlers.py (who gets what), status.py, models.py
│  │  └─ routes_dev.py     GET /api/v1/dev-mail/latest (dev transport in development/test only)
│  ├─ projects/            projects, towers, configurations, … and the catalogue (Phase 4)
│  │  ├─ models.py         tables (0002_catalogue); vocab.py = the allowed values (enums)
│  │  ├─ schemas*.py       request/response shapes: shared values, project, children, catalogue
│  │  ├─ fields.py         bounded string/number types for request bodies (SECURITY.md §5)
│  │  ├─ common.py         audit diffs, outbox events, project lock, slugs, 409 on clashes
│  │  ├─ service.py        list, create, update/archive, delete, publish, unpublish;
│  │  │                    duplicate.py copies a project with its children
│  │  ├─ project_input.py  body → columns and the rules across fields (ranges, pin, locality)
│  │  ├─ children.py       the five operations for every child list; child_kinds.py = per kind
│  │  ├─ catalogue.py      cities, localities, amenities ("used by N projects" guards)
│  │  ├─ blockers.py       publish blockers: the one place that decides "ready to publish"
│  │  ├─ media_owners.py   what media calls: an owner's project (locked), share-image use
│  │  ├─ present.py        rows → responses; display.py = ₹ and area strings (twin of
│  │  │                    packages/ui/src/format, same test vectors)
│  │  ├─ maps.py           Google Maps pin resolver (SSRF rules in its header); pluscode.py
│  │  ├─ routes.py, routes_children.py, routes_catalogue.py   HTTP only
│  │  └─ seed.py           amenity catalogue and `seed --sample` (D-015)
│  ├─ media/               the media library, links to owners, uploads (Phase 4 part 2, D-033)
│  │  ├─ models.py         media, upload_intent, media_link (exclusive arc); vocab.py = lists + limits
│  │  ├─ store.py          the MediaStore interface and get_store(); cloudinary_store.py (official
│  │  │                    SDK), fake_store.py (files in MEDIA_DEV_DIR, no network)
│  │  ├─ signing.py        Cloudinary-compatible upload and reply signatures; credentials.py
│  │  ├─ sniff.py          photo magic bytes + Pillow size check; multipart.py = capped body reader
│  │  ├─ scrub.py          strips EXIF/GPS, XMP, IPTC, comments from photos before any store sees them
│  │  ├─ uploads.py        photos through the API, upload signatures, confirm (intent rules)
│  │  ├─ links.py          attach / show-hide / cover / detach / reorder; rules.py = roles per owner
│  │  ├─ library.py        list, rename/alt/label, delete; events.py; handlers.py (destroy at store)
│  │  ├─ queries.py        what the projects module reads (gallery, cover, RERA QR, floor plans…)
│  │  ├─ content_links.py  what content calls: page block and post cover links, library facts
│  │  ├─ usage.py          where a file is used (delete refused while used; GET …/usage)
│  │  ├─ routes.py         /admin/media/**, /admin/media-links/**; routes_dev.py = /dev-media/**
│  │  │                    (fake store only)
│  │  └─ seed.py           SAMPLE placeholder tiles for `seed --sample` (fake store only)
│  ├─ content/             consent texts (part 3); pages, blocks, posts, FAQs, offers and
│  │  │                    testimonials (Phase 4 part 4)
│  │  ├─ models.py         consent_text, page, block, post, faq, offer, testimonial; vocab.py
│  │  ├─ consent.py        drafts, publish (draft wording refused in production), the current
│  │  │                    text, dev/test seed; routes.py = /admin/consent-texts/**
│  │  ├─ blocks.py         one strict `data` shape per block type; block_types.py = the
│  │  │                    Block/BlockInput unions; fields.py = no-HTML text, safe links
│  │  ├─ block_refs.py     ids a block names, checked and read FOR SHARE (library kind + honest
│  │  │                    label, projects…)
│  │  ├─ pages.py          pages: create, edit, archive, delete, publish (legal.publish, draft
│  │  │                    text, schedule rights, required pages, stale saves); page_blocks.py =
│  │  │                    PUT blocks; page_rules.py = blockers, guarded legal pages
│  │  ├─ posts.py, faqs.py, offers.py (+ offers_state.py), testimonials.py
│  │  ├─ schedule.py       the schedule tick (scheduled pages, offer start/end), run before
│  │  │                    each drain
│  │  ├─ media_uses.py     what media calls: share images, offer images, testimonial photos;
│  │  │                    media_changes.py = events when a file used by live content changes
│  │  ├─ queries.py        what seo and projects call: what is live at a path, content naming
│  │  │                    a project (its delete is refused)
│  │  ├─ present.py        rows → responses; routes_pages.py, routes_marketing.py   HTTP only
│  │  └─ seed.py           required system + legal pages (D-017 placeholder); sample post/offer/FAQs
│  ├─ seo/                 redirects (one hop, no loops, auto on slug changes), seo checks and
│  │                       warnings, public paths (paths.py); routes.py = /admin/redirects/**
│  ├─ leads/               public intake, inbox, pipeline, visits, export, report (Phase 4 part 3)
│  │  ├─ models.py         lead, lead_consent, lead_note, lead_activity, site_visit; vocab.py
│  │  ├─ phone.py          Indian numbers → E.164 (the rule and its DoT/TRAI sources in its header)
│  │  ├─ access.py         SECURITY.md §1: without leads.read_all you see only your own leads
│  │  │                    (others answer 404) — every read and write goes through it
│  │  ├─ intake.py         public enquiries, site-visit and brochure requests: consent check,
│  │  │                    rate limits, honeypot; creation.py (row, consent, duplicate link),
│  │  │                    routing.py (single / round robin / manual, D-016)
│  │  ├─ service.py        inbox, pipeline, owner, read/unread, notes, timeline, manual leads;
│  │  │                    filters.py (query → SQL), effects.py (timeline, audit, events)
│  │  ├─ visits.py         site-visit calendar and changes; report.py = UTM counts
│  │  ├─ export.py         streamed CSV (formula-safe, capped, audited)
│  │  ├─ erasure.py        erase on request and the retention clean-up (SECURITY.md §8)
│  │  ├─ present.py        rows → responses; queries.py = what projects and the dashboard call
│  │  ├─ routes_public.py, routes.py, routes_visits.py   HTTP only
│  │  └─ seed.py           12 sample leads and 4 visits for `seed --sample` (D-015)
│  ├─ dashboard/           GET /admin/dashboard: counts with links, latest leads, visits, tasks
│  ├─ integrations/        outbox drain + handlers, internal drain endpoint
│  ├─ worker.py            empire-worker loop (paid always-on hosting)
│  └─ cli.py               empire-api commands
└─ tests/                  pytest against a real PostgreSQL database
```

## Commands

Run everything from `apps/api/`. The root `.python-version` makes uv use Python 3.14.

```bash
uv sync                                        # install (creates .venv)
uv run alembic upgrade head                    # migrate the database in DATABASE_URL
uv run empire-api seed                         # flags, settings, amenity catalogue, system and legal
                                               #   pages as drafts (idempotent); in development/test
                                               #   also the DRAFT consent texts, current
uv run empire-api seed --sample                # + "Sample — Project A/B" (dev/demo only; refused in production),
                                               #   SAMPLE placeholder tiles in their photos (fake store only)
                                               #   12 "Sample Lead N" leads with 4 site visits, a
                                               #   SAMPLE post, offer and FAQs (never a testimonial),
                                               #   and 4 "Sample …" staff accounts (dev/test; invited,
                                               #   no password, no email)
uv run uvicorn empire_api.main:app --reload    # API on http://localhost:8000 (docs at /api/docs)
uv run empire-worker                           # optional: worker loop (schedule tick + drain + daily clean-up)

uv run ruff check && uv run ruff format --check
uv run mypy src                                # strict
uv run pytest -q                               # needs PostgreSQL; see "Tests" below
uv export --frozen --no-emit-project --all-groups -o /tmp/req.txt && uv run pip-audit -r /tmp/req.txt --disable-pip --strict   # known vulnerabilities (same as CI)

uv run empire-api gen-secrets                  # fresh values for YOUR local .env
uv run empire-api create-superadmin --email admin@empirebuildcon.com   # once per environment
uv run empire-api reset-two-factor --email someone@empirebuildcon.com   # break-glass: lost phone AND recovery codes
uv run empire-api openapi --out ../../packages/api-client/openapi.json  # after changing routes
```

`create-superadmin` prints a one-time setup link (24 hours). Nobody ever types a password for someone else; staff invited from the CMS get the same kind of link, by email only (the API never returns it).

`reset-two-factor` is for when nobody can sign in to use the CMS's "Reset two-factor" (the only super-admin lost both their phone and their recovery codes). It needs shell access to the server, is audited without an actor, signs the account out everywhere and queues the security email.

## Tests

The tests use a real PostgreSQL database, by default `postgresql+psycopg://empire:empire@localhost:5432/empire_test`; set `TEST_DATABASE_URL` to use another. The first test drops and recreates the `public` schema, so **never point it at a database you care about**. Then it runs the migrations, and every test starts from empty tables.

Important guards:
- `test_no_route_ever_redirects` calls every route with and without a trailing slash and fails on any 3xx. This is the Current Investor bug (ARCHITECTURE §3).
- `test_every_route_declares_who_may_call_it` fails if a route has no permission marker.
- `test_models_match_the_migrated_database` fails if a model changed without a migration.
- `test_projects_and_catalogue_match_the_design_contract`, `test_media_operations_match_the_design_contract` and `tests/test_leads_contract.py` fail if a Projects, Catalogue, Media, Lead intake, Leads, Dashboard or consent-text operation drifts from `handbook/api/openapi-v1.yaml` (method, path, operationId, permission; lead schemas keep every contract field, renames listed in the test).
- `tests/test_leads_access.py` checks the object-level rule on every lead surface (inbox, detail, notes, activity, writes, visits, export, report, dashboard): someone else's lead is 404.
- `test_round_robin_is_fair_under_concurrency` sends twelve enquiries at once to three people and expects exactly four each; it fails if the round-robin row lock is removed.
- `test_erasure_leaves_a_stub_and_nothing_personal_anywhere` scans every table for the erased person's details.
- The part 4 review fixes have their regression tests next to the feature: `tests/test_seo_redirects.py` (no `//host` targets, case-insensitive reserved paths, query kept when a chain collapses, no redirect from a live address), `tests/test_content_legal.py` (scheduled legal pages need `legal.publish`, no DRAFT text on a live legal page in production, required pages), `tests/test_content_edits.py` (stale saves, `canonical_path`, HTML and limits in SEO and translations), `tests/test_content_references.py` (FOR SHARE reads, project delete refused while content names it), `tests/test_content_schedule.py` (a stale `publish_at` never brings a page back) and `tests/test_content_media_use.py` (relabel events, labels on covers and offer images, testimonial initials).
- `tests/test_leads_review_privacy.py` and `tests/test_leads_review_rules.py` hold the regression tests from the part 3 review: duplicate links never name another owner's lead, erasure leaves no free text (scanned across every table) and covers the duplicate group or the whole person, the export audit keeps no search text, the export needs `X-CSRF-Token`, an IPv6 /64 is one network for every limit, editing a confirmed visit doesn't move its lead again, every dashboard count equals the total of the list its link opens, BHK is in half steps, and "fancy" numbers operators sell (99999 99999, 98765 43210) stay accepted.
- `test_dev_media_routes_exist_only_with_the_fake_store` fails if the fake store's routes could exist with the real store, and `test_the_dev_mailbox_exists_only_with_the_dev_transport_in_dev_or_test` does the same for `/api/v1/dev-mail/latest`.
- Part 5 (settings, users, two-factor, email):
  - `tests/test_two_factor.py`: the RFC 6238 Appendix B vectors, replay refusal (each 30-second step once), the 202 second step and its cookie, single use, expiry and network binding, lockout on wrong codes (a right password doesn't reset the counter), forced set-up with the flag on, recovery codes, turning it off, the super-admin's reset and the break-glass CLI, the `admin_2fa` rule, and no secret, code or token in logs, audit rows or events.
  - `tests/test_mail_transport.py`: Resend's request shape and headers against a mocked httpx, retried versus permanent failures, a stable idempotency key, a retry reaching only the people not yet reached, the dev mailbox, and the staging/production configuration rules.
  - `tests/test_mail_handlers.py`: every email event's handler, `alert: false` sends nothing, no full phone, email or message in any lead email, links never logged, dead links and inactive accounts skipped, the lock notice once an hour, and the dashboard's "emails couldn't be sent".
  - `tests/test_settings.py`: every group's rules and permissions (marketing.tracking, seo.manage, super-admin for retention), the fixed RERA fields, lead routing checks, audit diffs and the integrations block without the key.
  - `tests/test_settings_contract.py`: the Auth, Settings and Users operations against the design contract, with the additions and the one changed permission listed.
  - `tests/test_part5_review_fixes.py`: the part 5 review's findings (M1–L11), each named: open sign-in challenges die with the sessions and with a password change, the password-change endpoint counts on the lockout, a rotation member who left never blocks saving, only the newest setup/reset link works, switching `admin_2fa` on signs out admins without two-factor, the database refuses UPDATE/DELETE on `audit_log`, and link tokens travel in the URL fragment.
  - `tests/test_lead_owners_and_reset_quota.py`: invited (and deactivated) accounts are never given leads on any path, and password-reset requests are capped at 5 per email per UTC day on top of 3 an hour, with identical answers for real and unknown emails.
- `tests/test_display.py` runs the same money and area vectors as `packages/ui/test/format.test.ts`; change both together.

Fixtures worth knowing (tests/conftest.py):
- `no_network` (automatic): the maps resolver's real HTTP client fails any test that reaches it. Short-link tests inject a fake client (`httpx.MockTransport`).
- `no_network` also replaces the Cloudinary SDK's HTTP clients with ones that fail the test. Cloudinary-store tests replace the SDK functions (`cloudinary.uploader.upload`, `cloudinary.api.resource`, …) instead.
- `no_network` also makes the Resend transport's default httpx client fail the test; transport tests pass a client with `httpx.MockTransport`. Email in tests goes to the dev transport in a temporary `MAIL_DEV_DIR`, emptied before each test; `two_factor_support.mail_to(address)` drains the outbox and reads it.
- `two_factor_support.use_clock(monkeypatch)`: the two-factor module's clock, so a test can move to the next 30-second step (a code is accepted once per step).
- Media tests run on the fake store (no `CLOUDINARY_URL`), writing to a temporary `MEDIA_DEV_DIR`.
- `qr_present`: pretends every project has its RERA QR image, for publish tests that aren't about media. `tests/test_media_projects.py` uploads a real QR through the fake store instead.
- `texts`: the draft lead-form and marketing consent texts, current, as `empire-api seed` makes them in development; returns `{kind: {id, version}}` for the public form bodies (`tests/leads_support.py` builds them).
- `intake_unlimited`: lifts the public intake limit (5 per 10 minutes per IP and phone), because every TestClient call comes from one address. `tests/test_leads_intake.py` tests the real limits, with the edge key for different IPs.
- `sales_pair`: two sales users, each signed in with their own client.
- `leads_support.captured_logs(monkeypatch)`: every structured log line written in a block, for "no phone number in the logs" checks (module loggers cache their output, so it swaps in fresh ones).

## Adding a staff route

```python
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from empire_api.db import get_db
from empire_api.errors import ApiProblem, problem_responses
from empire_api.platform import audit, outbox
from empire_api.platform.crypto import client_ip
from empire_api.users.deps import require, staff
from empire_api.users.sessions import SessionInfo

router = APIRouter(prefix="/api/v1/admin", tags=["Things"],
                   responses=problem_responses(401, 403, 404, 422))

@router.patch("/things/{key}", operation_id="update_thing", **staff("things.write", write=True))
def update_thing(key: str, body: ThingUpdate, request: Request,
                 actor: Annotated[SessionInfo, Depends(require("things.write"))],
                 db: Annotated[Session, Depends(get_db)]) -> Thing:
    ...change the row...
    audit.record(db, action="thing.updated", entity_type="thing", entity_id=key,
                 actor_id=actor.user.id, ip=client_ip(request), changes=audit.diff(before, after))
    outbox.emit(db, type_="thing.updated", aggregate_type="thing", aggregate_id=key,
                actor_id=actor.user.id, data={"key": key})
    db.commit()      # one commit: change + audit row + event together
```

Checklist for a new route:
1. **Permission.** Use `staff(...)`: it both enforces the permission and publishes it in the spec. Take `require(...)` as a parameter only when you need the signed-in user (it runs once per request). The permission must exist in `users/roles.py`; adding one or changing a role needs owner approval (CONTRIBUTING §7).
2. **Public routes.** Use `**PUBLIC` instead, and add rate limits (`platform.rate_limit.enforce`).
3. **Request bodies.** Staff bodies use `extra="forbid"`, and every string has a length limit.
4. **Audit and events.** Write an audit row for every create, update, delete, publish and export, and an outbox event for anything others react to (ARCHITECTURE §9).
5. **Spec.** Run `empire-api openapi` and regenerate the web client (`pnpm api:client` at the repo root). CI fails if the committed spec is stale.
6. **Tests.** Cover success, validation and permission denied.

## Configuration

All settings are environment variables. They are listed in the repo's `.env.example` and in SECURITY.md §7. The API-only extras are:

| Variable | Default | Meaning |
|---|---|---|
| `EDGE_PROXY_KEY` | empty | Shared secret with the web proxy (`apps/web/src/proxy.ts`). When set, calls without it get 403 (except health checks and `/api/v1/internal/*`), and only then is the client IP read from `X-Empire-Client-IP`. Empty locally; required in staging and production (D-027). `X-Forwarded-For` is never trusted. |
| `CLOUDINARY_URL` | empty | `cloudinary://<api_key>:<api_secret>@<cloud_name>`. Required in staging and production. The secret stays on the server; only the cloud name and API key reach the browser, inside an upload signature (SECURITY.md §7). |
| `MEDIA_STORE` | empty | `cloudinary` or `fake`. Empty: `cloudinary` when `CLOUDINARY_URL` is set, otherwise `fake`. Staging and production refuse `fake`. |
| `MEDIA_DEV_DIR` | `apps/api/.media-dev/` | Where the fake store keeps files (git-ignored). Served at `/api/v1/dev-media/files/…`, which exists only while the fake store is active, as does its Cloudinary-shaped `/api/v1/dev-media/upload/{resource_type}`. |
| `EMAIL_API_KEY` | empty | The Resend API key. Required in staging and production. Sent only to `api.resend.com` in the Authorization header; never logged, stored or returned (Settings shows "set in the server environment"). |
| `EMAIL_FROM` | empty | The plain sender address (no display name; that comes from the `email` settings group) on a domain verified at Resend. Required in staging and production. |
| `EMAIL_TRANSPORT` | empty | `resend` or `dev`. Empty: `resend` when `EMAIL_API_KEY` is set, otherwise `dev`. Staging and production refuse `dev`. |
| `MAIL_DEV_DIR` | `apps/api/.mail-dev/` | Where the dev transport keeps messages as JSON (git-ignored; they hold setup and reset links). `GET /api/v1/dev-mail/latest?to=<email>` reads the newest one; it exists only with the dev transport and `APP_ENV` development or test. |
| `DB_POOL_SIZE` | `5` | Connections per process |
| `WORKER_DRAIN_INTERVAL_SECONDS` | `30` | Tick length of `empire-worker` |

Business settings live in the database (`setting` rows, one per group), edited in the CMS's Settings screen (`/admin/settings`); `site_settings/groups.py` lists every group's fields and who may change it. Two that the API itself acts on:
- `lead_routing`: `mode` is `single` (default: the sales inbox, or the person in `single_owner_user_id`), `round_robin` (the people in `round_robin_user_ids`, or every sales user who can sign in when empty, skipping `round_robin_paused_user_ids`) or `manual`. Only accounts that are active, have set their own password (not just invited) and can open leads are ever given a lead (`leads/routing.owner_refusal`): routing skips the others, and Settings, assignment and manual leads refuse them with 422. The round-robin turn is kept in `system.lead_round_robin`. `inbox_email` gets every new-lead and site-visit email; when it is empty they go to every active super-admin.
- `privacy.lead_retention_years` (default 3, 1–10, super-admin only): the daily clean-up anonymises leads with no activity for that long (SECURITY.md §8).
- Public intake answers 503 until a `lead_form` consent text is published. `empire-api seed` publishes DRAFT texts in development and test only.

The maps resolver (`POST /api/v1/admin/maps/resolve`) needs outbound HTTPS to Google's short-link hosts only (`maps.app.goo.gl`, `goo.gl`); long links and plus codes are read without any network call.

Email needs outbound HTTPS to `api.resend.com` only (`POST /emails`, 10-second timeout). Events that send email are retried on the outbox schedule (1 min … 24 h) when Resend is down, rate-limits, or the Free plan's 100-a-day quota is used up (it resets at midnight UTC); a message Resend refuses as invalid makes its event dead at once, and the dashboard's "Needs attention" counts emails that couldn't be sent in the last 7 days.

Setup and reset links are `<SITE_URL>/admin/setup#token=…` and `/admin/reset#token=…`: the token is in the fragment, which browsers never send to a server, so it stays out of the web host's request logs. Only the newest link of an account works.

The audit log is append-only in the database as well: a trigger from migration 0006 refuses UPDATE and DELETE on `audit_log` (tests empty it with TRUNCATE, which row triggers don't see).

Two-factor sign-in (TOTP) is for admin and super-admin accounts: asked whenever an account has it on, and, with the `admin_2fa` flag on, set up at sign-in by anyone in those roles who hasn't. The flag can be switched on only by a super-admin who has it on. Secrets are stored encrypted with `DATA_ENCRYPTION_KEY` and recovery codes as keyed hashes of it, so changing that key means everyone sets two-factor up again.

The Cloudinary store needs outbound HTTPS to `api.cloudinary.com` (uploads, Admin API, destroy). Files are delivered from `res.cloudinary.com`. Videos and documents go from the browser straight to `api.cloudinary.com`, so the Phase 5 CSP needs `connect-src https://api.cloudinary.com` and `img-src https://res.cloudinary.com`.

In development and test, missing secrets fall back to clearly insecure defaults so the app runs on a fresh clone. In staging and production, the app refuses to start without real values.

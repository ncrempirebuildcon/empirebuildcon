# Empire website and CMS: security plan

**Phase 1 deliverable** · 18 Oct 2026 · Status: for review
Applies from Phase 3. Each item lists where it is enforced and how it is tested. Related: [ARCHITECTURE.md](ARCHITECTURE.md), [DECISIONS.md](DECISIONS.md) D-009.

---

## 1. Authentication

| Control | Design | Test |
|---|---|---|
| Passwords | Argon2id (`argon2-cffi`, library defaults or stronger), minimum 12 characters, no maximum below 200, checked against a list of common passwords. No composition rules. | Unit tests on hashing, policy |
| Session | Signed JWT (HS256, `SESSION_SECRET` ≥ 32 random bytes) carrying `sub` (user id), `sid` (session id), `iat`, `exp`. The `session` table is checked on every request, so logout, password change and "sign out everywhere" take effect at once. | API tests: revoked session → 401 |
| Cookie | `__Host-empire_session`; `HttpOnly; Secure; SameSite=Lax; Path=/`; no `Domain`. Nothing in localStorage or sessionStorage. | Playwright checks cookie flags |
| Lifetime | 8 hours idle, 7 days absolute; rotated (new `sid`) at login and on privilege change. | API tests |
| Lockout | Every sign-in attempt is counted per **account and network (IP)** before the password is checked; the 6th attempt in a 15-minute window gets 429 until the window ends. A stranger can't lock the owner out from another network, parallel requests can't get past 5 guesses, and unknown emails behave exactly like real ones (same 401, same 429). Super-admin unlock clears every network's counter. Same error message for unknown email and wrong password. (D-027) | API tests incl. parallel guesses |
| Rate limits | Login: 10 per 15 min per network; password-reset requests: 3 per hour and 5 per UTC day per email, and 10 per hour per network (the daily cap keeps one targeted address from using up the email quota). A "network" is the IPv4 address, or the /64 for IPv6 (IPv4-mapped addresses count as their IPv4), so rotating addresses inside one IPv6 allocation doesn't help. Counters in PostgreSQL (`rate_limit_bucket`), shared by every API instance. | API tests incl. two app instances and IPv6 /64 |
| Client IP and edge key | Only our web proxy may call the API: it adds `X-Empire-Edge-Key` (`EDGE_PROXY_KEY`, required in staging and production) and the visitor's IP as seen by the host in `X-Empire-Client-IP`, after removing any `X-Empire-*` header the visitor sent. The API refuses calls without the key (403), except health checks and the scheduler's internal calls, and never reads `X-Forwarded-For`. `/api/v1/internal/*` is not reachable through the website. (D-027) | API tests, Playwright |
| Password reset | Single-use random token (32 bytes), stored hashed, valid 30 minutes, claimed with one conditional update so two requests can't both use it; a reset or password change burns every other open link and revokes all sessions. | API tests |
| Super-admin bootstrap | First super-admin is created by a one-time CLI command (`empire-api create-superadmin --email admin@empirebuildcon.com`) that prints a one-time setup link, never a password. No default credentials exist. | Manual check at deploy |
| Two-factor | TOTP (our own RFC 6238 code: HMAC-SHA1, 30-second steps, 6 digits, ±1 step; tested with the RFC's Appendix B vectors) for admin and super-admin accounts. The secret is stored Fernet-encrypted; ten single-use recovery codes are stored as keyed hashes (key derived from `DATA_ENCRYPTION_KEY`) and shown once. Each time step is accepted once per account, so a code can't be replayed. An account with two-factor on is always asked for a code. Flag `admin_2fa` additionally forces admins and super-admins without it to set it up at sign-in; only a super-admin can switch the flag, and only after turning two-factor on for their own account. (D-036) | API tests incl. RFC vectors, replay, lockout |
| Two-step sign-in | With two-factor, a correct password creates **no** session: the API answers 202 and sets `__Host-empire_2fa` (HttpOnly, Secure, SameSite=Strict, 5 minutes, single use, bound to the account and network). The code then creates the real session. Wrong codes count on the same per-account-and-network lockout as passwords; a correct password with a code still pending doesn't reset it; codes are also capped at 20 per account per hour across networks. | API and browser tests |
| Account proof | Changing the password counts a wrong current password on the sign-in lockout and audits it. Revoking sessions (reset, change, sign out everywhere, deactivate, role change, two-factor reset, switching `admin_2fa` on) also closes open sign-in challenges, and a challenge opened before the last password change is refused. Setting up two-factor from My account needs the password; turning it off needs the password and a code; new recovery codes need a code. Turning it on signs out the account's other sessions. A super-admin can reset someone's two-factor (signs them out everywhere, audited, security email). Break-glass for a lone super-admin who lost both phone and codes: `empire-api reset-two-factor --email …` on the server. | API tests |
| Setup and reset pages | Links carry the token in the URL fragment (`/admin/setup#token=…`), which browsers never send to the server, so it can't reach request logs. Issuing a link burns older open links, and so do an email change and deactivate/reactivate. `/admin/setup` and `/admin/reset` read the token once, remove it from the address bar, send it only in the request body, set `Referrer-Policy: no-referrer` and load nothing from other sites. The API never returns a link; links travel only by email, encrypted in the outbox. | Browser tests |

## 2. Authorisation

- Every staff route declares its permission (`x-permission` in the OpenAPI spec). A test walks all routes and fails if one has no permission or public marker.
- Object-level checks: sales users without `leads.read_all` only see their own leads, in lists, detail, notes, activity, site visits, exports, reports and the dashboard. Requests for someone else's lead answer 404, so lead ids can't be probed (`leads/access.py`).
- The CMS hides controls a role cannot use, but the API is the only gate.
- A route's permission marker and its check come from one helper (`staff()`), so a route can't advertise a permission it doesn't enforce.
- There is always at least one active super-admin who can sign in; demoting or deactivating the last one is refused (rows locked against races).

## 3. CSRF and CORS

- Staff writes (`POST/PATCH/PUT/DELETE`) need the `X-CSRF-Token` header matching the token bound to the session (returned by `/auth/me`). SameSite=Lax is the second layer.
- Public lead endpoints accept no cookies' authority (they don't read the session), so CSRF does not apply; rate limits and the honeypot do.
- CORS is closed in production (same-origin through the proxy). Allowed origins come from settings only for local development.

## 4. HTTP security headers

Set by the web app (pages) and the API (JSON responses):

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (add `preload` one month after go-live if nothing breaks) |
| `Content-Security-Policy` | Nonce-based `script-src` for Next.js; `img-src 'self' https://res.cloudinary.com data: *.tile.openstreetmap.org`; `connect-src 'self' https://api.cloudinary.com` (the CMS uploads videos and documents straight to Cloudinary; add `api-eu`/`api-ap` only if the account lives there) plus Sentry ingest host and analytics hosts only when consented tools are enabled; `frame-ancestors 'none'`; `form-action 'self'`; `object-src 'none'`; `base-uri 'self'`. Report-only by default (`Content-Security-Policy-Report-Only`), enforced with `CSP_ENFORCE=true` (D-039). |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | camera, microphone, geolocation, payment all `()` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cache-Control` on `/admin/**` and API staff routes | `no-store` |

Tested by a Playwright check and a header assertion in API tests.

## 5. Input, output and injection

- Pydantic models with strict types and length limits on every request body; unknown fields rejected on staff routes.
- SQL only through SQLAlchemy with bound parameters; no string-built SQL.
- Formatted text is parsed by our own renderer into React elements; `dangerouslySetInnerHTML` is banned by lint rules (on DOM elements, components and `createElement`) in the web app and the UI package, except for JSON-LD, which is serialised with escaping.
- **No HTML in content.** Every content text field refuses HTML (a tag, `<!--`, `<!doctype`) with a plain-text message; `a < b` is fine. Page blocks are typed per block type, so no free-form data is stored.
- **Links in content** (block buttons, offer buttons and terms links): a site path starting with one `/`, or `https://` with a host. Refused: `javascript:`, `data:`, `vbscript:`, `http:`, `mailto:`, protocol-relative `//host`, spaces and `user@host` tricks. Videos are YouTube/Vimeo links from a host allowlist, stored as provider and id, so the page only ever embeds that provider's player.
- **Redirects:** `from_path` is a site path (not `/`, and never under `/admin`, `/api`, `/_next` or `/_internal`, in any letter case). `to_path` is a site path or `https://` on one of our own domains, stored as its path, so there are no open redirects. The stored path never starts with `//` and never holds a backslash (`https://empirebuildcon.com//evil.example` is refused), and a database CHECK backs that up. Loops are refused and chains collapse to one hop.
- **Site paths** (`seo.canonical_path`, CTA links, redirect targets) refuse every whitespace and control character: browsers drop tabs and newlines, which would turn `/<tab>/evil.example` into another host.
- **SSRF:** the maps resolver (`apps/api/src/empire_api/projects/maps.py`) follows short links only:
  - Hosts: an explicit list (google.com, www.google.com, maps.google.com, google.co.in, www.google.co.in, maps.google.co.in, goo.gl, maps.app.goo.gl). There are no wildcards.
  - Paths: the `www.` and `goo.gl` hosts must also be on a `/maps` path, which keeps Google's open redirect out.
  - Every hop must be `https://`, with at most 5 redirects. Only headers are read, never a body.
  - The whole lookup has a hard 5 s limit, DNS included.
  - Each user may make 30 lookups per 10 minutes (D-031). Webhook URLs must be `https://`, and are refused if they resolve to private, loopback or link-local addresses (checked at save and at each delivery).

## 6. Uploads

- **Photos:**
  - Magic-byte check: JPEG, PNG, WebP and AVIF only. SVG, HEIC, GIF and anything else get 415.
  - Size: at most 10 MB, counted while streaming, not just from Content-Length.
  - Pixels: at most 25 MP. The image is decoded with Pillow.
  - The filename is discarded; the public id is generated.
  - EXIF, GPS, XMP, IPTC and comments are stripped on the server before upload, so the stored original carries no location data (D-033, `media/scrub.py`).
    - A photo with no metadata passes through byte for byte.
    - Otherwise the orientation is applied and the file is re-encoded in the same format. The ICC colour profile is kept, because it describes colours, not people.
  - Animated images are refused.
  - Data appended after the image's real end is cut off.
- **Videos:** container metadata (phones can record GPS) isn't stripped yet. This is checked on staging in Phase 9 (D-033).
- **SVG uploads are refused** (script risk). The logo kit SVGs ship in the code, not through uploads.
- **Videos and documents:**
  - Allowed types: MP4, MOV and WebM; PDF, DOC, DOCX, PPT and PPTX.
  - The upload signature is scoped to one public id and folder, and signs `overwrite=false`.
  - The API's `upload_intent` limits it to 60 minutes (Cloudinary's own signature lifetime), the requesting user and one use.
  - Refused, expired and never-confirmed uploads are destroyed under every resource type, and again after the hour has passed, so nothing is left behind at the store.
  - The reply signature covers only `public_id` and `version`. That is why the API also re-reads the asset from the Admin API (type, bytes, format) before saving, and destroys it if anything is off.
- **Delivery:**
  - PDFs open in the browser.
  - Office files download.
  - Cloudinary strips metadata from transformed images, and every image URL we build carries a transformation.
- **Rate limit:** uploads and signatures share one budget of 120 per 10 minutes per user.
- **Fake store:** only `FakeStore` serves `/api/v1/dev-media/**`. Staging and production refuse to start with it.

## 7. Secrets

- Only in environment variables on each host. The repo has `.env.example` with names and placeholder values only.
- CI runs a secret scan (gitleaks) on every push and blocks the build on a hit.
- Webhook signing secrets are stored encrypted (Fernet, key `DATA_ENCRYPTION_KEY` from the environment) because they must be readable to sign; they are shown once at creation.
- Third-party API keys (Cloudinary, email, Meta, Google) never reach the browser, except Cloudinary's public cloud name and API key needed for signed direct upload (the secret stays on the server).
- If a secret is ever pasted in chat, committed or logged: rotate it at the provider, update the host env var, redeploy, and note it in the decisions log (without the value).

| Variable | Used by |
|---|---|
| `DATABASE_URL` | API, worker |
| `SESSION_SECRET`, `DATA_ENCRYPTION_KEY`, `INTERNAL_API_KEY`, `REVALIDATE_SECRET` | API, worker, web (revalidate only) |
| `CLOUDINARY_URL` | API |
| `EMAIL_API_KEY`, `EMAIL_FROM` (Resend, D-007; staging and production refuse to start without them or with the dev mailbox) | API, worker |
| `SENTRY_DSN_API`, `NEXT_PUBLIC_SENTRY_DSN` | API, web |
| `API_ORIGIN` | Web (rewrite target) |

## 8. Personal data (leads)

India's Digital Personal Data Protection Act applies to lead data. The design supports it; the legal texts are Claude drafts approved by the owner (D-017).

- Collect only what the form needs: name, phone, optional email and message.
- Consent recorded per lead with the exact text version; marketing use (ad platforms) needs its own consent.
- IP addresses are stored only as a salted hash, for abuse checks. IPv6 addresses are keyed by their /64 network for rate limits and lockout. Rate-limit keys use a keyed hash of the phone.
- Visitor enquiries write no audit row: the lead's timeline covers them, and an audit row would copy the visitor's network into another table.
- Page URLs must be http(s) or site paths, and referrers http(s), so a `javascript:` link can't reach a staff browser.
- Access limited by role; CSV export only for admin and super-admin, and every export is audited.
- Erasure on request: `leads.erase` replaces personal fields with a stub and keeps the audit trail. That includes free text, notes and event payloads. Audit rows never receive personal free text in the first place, so they need no scrubbing. It covers the lead's duplicate group and, on request, every lead with the same phone (D-034).
- Retention: leads inactive for 3 years are anonymised by the daily clean-up job (setting `privacy.lead_retention_years`, 1–10; only the super-admin can change it in Settings). Reads and exports don't count as activity.
- Lead emails (new lead, assigned, site-visit request) carry the reference, project, source, name and a **masked** phone, plus a link to the CMS. Never the full phone, email or message: emails get forwarded and kept.
- The audit log shows IP addresses masked (the first two IPv4 parts, or the IPv6 /32).
- Logs and audit diffs mask phone numbers and never contain form bodies.
- Error reports (Sentry) never include local variables, request bodies or cookies, so a crash during sign-in can't send a password; password fields are hidden from `repr`.

## 9. Dependencies and code

- Lockfiles committed (`pnpm-lock.yaml`, `uv.lock`). Renovate or Dependabot opens update PRs weekly; security updates immediately.
- CI: `pip-audit` and `pnpm audit --prod` fail on high/critical issues; `ruff`, `mypy`, ESLint and TypeScript strict mode.
- Branch protection on `main` once GitHub is set up: CI must pass before merge.

## 10. Backups and recovery

- Database: Neon's restore window (6 hours on the free plan), plus a **daily logical backup** (`pg_dump`, compressed, encrypted with a key only the owner holds) made by a GitHub Actions job and kept 30 days outside the database provider (D-007).
- Media: Cloudinary keeps originals; a monthly inventory export of public ids is kept with the database backup.
- A **real restore test** runs in Phase 8 and is recorded in handbook/RUNBOOK.md (written in Phase 9) with the date and how long it took.

## 11. Monitoring and incident response

- Sentry alerts on new error types; uptime alerts on site and `/api/health`.
- Audit log covers logins, failed logins, permission changes, exports, erasures, publishes.
- Runbook entries (handbook/RUNBOOK.md, Phase 9): suspected account compromise (revoke sessions, reset password, rotate `SESSION_SECRET` to sign everyone out), leaked secret (rotate), spam wave (switch on captcha flag), domain on hold (NIXI/registrar steps).

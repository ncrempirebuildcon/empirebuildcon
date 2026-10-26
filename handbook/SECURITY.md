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
| Rate limits | Login: 10 per 15 min per network; password-reset requests: 3 per hour per email and 10 per hour per network. A "network" is the IPv4 address, or the /64 for IPv6 (IPv4-mapped addresses count as their IPv4), so rotating addresses inside one IPv6 allocation doesn't help. Counters in PostgreSQL (`rate_limit_bucket`), shared by every API instance. | API tests incl. two app instances and IPv6 /64 |
| Client IP and edge key | Only our web proxy may call the API: it adds `X-Empire-Edge-Key` (`EDGE_PROXY_KEY`, required in staging and production) and the visitor's IP as seen by the host in `X-Empire-Client-IP`, after removing any `X-Empire-*` header the visitor sent. The API refuses calls without the key (403), except health checks and the scheduler's internal calls, and never reads `X-Forwarded-For`. `/api/v1/internal/*` is not reachable through the website. (D-027) | API tests, Playwright |
| Password reset | Single-use random token (32 bytes), stored hashed, valid 30 minutes, claimed with one conditional update so two requests can't both use it; a reset or password change burns every other open link and revokes all sessions. | API tests |
| Super-admin bootstrap | First super-admin is created by a one-time CLI command (`empire-api create-superadmin --email admin@empirebuildcon.com`) that prints a one-time setup link, never a password. No default credentials exist. | Manual check at deploy |
| Two-factor | TOTP for super-admin and admin accounts, behind flag `admin_2fa` (built in Phase 4, switched on before go-live if the owner agrees). Only a super-admin can switch this flag. | API tests |

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
| `Content-Security-Policy` | Nonce-based `script-src` for Next.js; `img-src 'self' res.cloudinary.com data: *.tile.openstreetmap.org`; `connect-src 'self' https://api.cloudinary.com` (the CMS uploads videos and documents straight to Cloudinary; add `api-eu`/`api-ap` only if the account lives there) plus analytics hosts only when consented tools are enabled; `frame-ancestors 'none'`; `form-action 'self'`; `object-src 'none'`; `base-uri 'self'`. Report-only for one week on staging first. |
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
- Slugs, redirects: `to_path` must be a site path or an allow-listed host; no open redirects.
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
| `EMAIL_API_KEY` (provider chosen in D-007) | Worker |
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
- Retention: leads inactive for 3 years are anonymised by the daily clean-up job (setting `privacy.lead_retention_years`; the owner can change it in Settings). Reads and exports don't count as activity.
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

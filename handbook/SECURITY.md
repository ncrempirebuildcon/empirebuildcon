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
| Lockout | 5 failed logins on an account → locked 15 minutes (counter in PostgreSQL). Super-admin can unlock. Same error message for unknown email and wrong password. | API tests |
| Rate limits | Login: 10 per 15 min per IP; password-reset requests: 3 per hour per email and 10 per hour per IP. Counters in PostgreSQL (`rate_limit_bucket`), shared by every API instance. | API tests incl. two app instances |
| Password reset | Single-use random token (32 bytes), stored hashed, valid 30 minutes; reset revokes all sessions. | API tests |
| Super-admin bootstrap | First super-admin is created by a one-time CLI command (`empire-api create-superadmin --email admin@empirebuildcon.com`) that prints a one-time setup link, never a password. No default credentials exist. | Manual check at deploy |
| Two-factor | TOTP for super-admin and admin accounts, behind flag `admin_2fa` (built in Phase 4, switched on before go-live if the owner agrees). | API tests |

## 2. Authorisation

- Every staff route declares its permission (`x-permission` in the OpenAPI spec). A test walks all routes and fails if one has no permission or public marker.
- Object-level checks: sales users without `leads.read_all` only see their own leads, in lists, detail, exports and reports.
- The CMS hides controls a role cannot use, but the API is the only gate.

## 3. CSRF and CORS

- Staff writes (`POST/PATCH/PUT/DELETE`) need the `X-CSRF-Token` header matching the token bound to the session (returned by `/auth/me`). SameSite=Lax is the second layer.
- Public lead endpoints accept no cookies' authority (they don't read the session), so CSRF does not apply; rate limits and the honeypot do.
- CORS is closed in production (same-origin through the proxy). Allowed origins come from settings only for local development.

## 4. HTTP security headers

Set by the web app (pages) and the API (JSON responses):

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (add `preload` one month after go-live if nothing breaks) |
| `Content-Security-Policy` | Nonce-based `script-src` for Next.js; `img-src 'self' res.cloudinary.com data: *.tile.openstreetmap.org`; `connect-src 'self'` plus analytics hosts only when consented tools are enabled; `frame-ancestors 'none'`; `form-action 'self'`; `object-src 'none'`; `base-uri 'self'`. Report-only for one week on staging first. |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | camera, microphone, geolocation, payment all `()` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cache-Control` on `/admin/**` and API staff routes | `no-store` |

Tested by a Playwright check and a header assertion in API tests.

## 5. Input, output and injection

- Pydantic models with strict types and length limits on every request body; unknown fields rejected on staff routes.
- SQL only through SQLAlchemy with bound parameters; no string-built SQL.
- Formatted text is parsed by our own renderer into React elements; `dangerouslySetInnerHTML` is banned by lint rule except for JSON-LD, which is serialised with escaping.
- Slugs, redirects: `to_path` must be a site path or an allow-listed host; no open redirects.
- **SSRF:** the maps resolver only follows `maps.app.goo.gl`, `goo.gl/maps` and `*.google.com` and stops after 3 hops, 5 s timeout. Webhook URLs must be `https://`, and are refused if they resolve to private, loopback or link-local addresses (checked at save and at each delivery).

## 6. Uploads

- Photos: magic-byte check (JPEG, PNG, WebP, AVIF), ≤ 10 MB, filename discarded (Cloudinary public id is generated), EXIF GPS stripped by Cloudinary transformation on delivery.
- SVG uploads are refused (script risk). The logo kit SVGs ship in the code, not through uploads.
- Video/documents: signature valid 10 minutes, scoped to one `public_id` and folder; the API verifies Cloudinary's reply signature and re-reads the asset (type, bytes) from the Admin API before saving. Allowed: MP4, MOV, WebM; PDF, DOC, DOCX, PPT, PPTX.
- Documents are delivered with `Content-Disposition: attachment` except PDFs, which open in a new tab.

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
- IP addresses stored only as a salted hash (for abuse checks).
- Access limited by role; CSV export only for admin and super-admin, and every export is audited.
- Erasure on request: `leads.erase` replaces personal fields with a stub and keeps the audit trail.
- Retention: leads inactive for 3 years are anonymised by the daily clean-up job (default; owner can change in Settings).
- Logs mask phone numbers and never contain form bodies.

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

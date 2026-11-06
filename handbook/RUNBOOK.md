# RUNBOOK · staging, production and go-live

How to put the site on its hosts, keep it running and bring it back. Written in task L3, before any account was touched. Every step here is checked on **staging first**, then repeated for production.

- **Who does what:** the owner signs in to every provider and pastes secrets into the provider's own secret store. Claude never sees a secret (AGENTS.md); it gives the steps, checks the result through the site and reads the logs the owner shares.
- **Hosts** ([ARCHITECTURE.md §19](ARCHITECTURE.md), D-007): see the table below.

| Piece | Host | Free plan | In this repo |
|---|---|---|---|
| Website (Next.js) | Netlify | Free | `apps/web/netlify.toml` |
| API | Google Cloud Run service `empire-api` (region `asia-south1`, Mumbai) | Free tier; billing account required | `apps/api/Dockerfile` |
| Migrations, owner account | Cloud Run jobs `empire-migrate`, `empire-admin` (same image) | Free tier | `alembic upgrade head`, `empire-api create-superadmin` |
| Background work (every 15 min) | Cloud Scheduler job `empire-drain` → `POST /api/v1/internal/outbox/drain` | 3 jobs free | D-010 |
| Database | Neon (PostgreSQL 18), region AWS `ap-south-1` | Free | — |
| Photos, videos, files | Cloudinary | Free | — |
| Email | Resend (domain verified) | Free | — |
| DNS, redirects | Cloudflare | Free | — |
| Errors | Sentry | Developer | — |
| Uptime | UptimeRobot | Free | — |
| Backups | GitHub Actions, daily, encrypted | — | `.github/workflows/backup.yml` |

Staging and production are separate: separate Netlify sites, Cloud Run services, Neon branches or projects, secrets, and Cloudinary folders.

## 1. Secrets and settings

Generate a fresh set for each environment, on the owner's own computer: `uv --directory apps/api run empire-api gen-secrets`. Never reuse the development values, never paste them into chat, and keep a copy in the owner's password manager.

### API (Cloud Run service, Secret Manager for the secrets)

| Name | Staging | Production | Secret? |
|---|---|---|---|
| `APP_ENV` | `staging` | `production` | no (the API refuses to start on Cloud Run without one of these, D-052) |
| `SITE_URL` | `https://staging.empirebuildcon.com` | `https://empirebuildcon.com` | no |
| `DATABASE_URL` | Neon staging, `postgresql+psycopg://…?sslmode=require` | Neon production | yes |
| `DB_POOL_SIZE` | `3` | `5` | no (keep the total under Neon's connection limit: each API instance opens up to 2 × `DB_POOL_SIZE` + 4 connections, the + 4 being the small pool for rate limits and the sent-email record, D-054) |
| `SESSION_SECRET`, `DATA_ENCRYPTION_KEY`, `INTERNAL_API_KEY`, `IP_HASH_SALT`, `REVALIDATE_SECRET`, `EDGE_PROXY_KEY` | from `gen-secrets` | from `gen-secrets` | yes (`DATA_ENCRYPTION_KEY` can't be changed later without losing encrypted data, so back it up) |
| `WEB_REVALIDATE_URL` | `https://staging…/_internal/revalidate` | `https://empirebuildcon.com/_internal/revalidate` | no |
| `CLOUDINARY_URL` | Cloudinary staging folder key | production key | yes |
| `EMAIL_API_KEY` | Resend key | Resend key | yes |
| `EMAIL_FROM` | `alerts@empirebuildcon.com` | same | no |
| `SENTRY_DSN_API` | Sentry API project | same | no |
| `CORS_ALLOWED_ORIGINS` | empty | empty | no (same-origin proxy) |

### Website (Netlify, Site configuration → Environment variables)

| Name | Value | Secret? |
|---|---|---|
| `APP_ENV` | `staging` / `production` | no |
| `SITE_URL` | as above | no |
| `API_ORIGIN` | the Cloud Run service URL (`https://empire-api-….a.run.app`) | no |
| `EDGE_PROXY_KEY`, `REVALIDATE_SECRET` | the **same** values as the API | yes |
| `CLIENT_IP_SOURCE_HEADER` | `x-nf-client-connection-ip` (check in §3) | no |
| `CSP_ENFORCE` | staging: unset for the first week (report only), then `true`. Production: unset (enforced by default) | no |
| `ALLOW_INDEXING` | unset until go-live; `true` on production at go-live only | no |
| `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_DSN` | Sentry web project | no |
| `REDIRECT_CACHE_SECONDS` | unset (60) | no |

## 2. First set-up (staging, then production)

1. **Neon:**
   - Create the project in AWS `ap-south-1`, PostgreSQL 18.
   - Create a `staging` branch; production uses `main` (or a separate project).
   - Copy each connection string ("pooled" off; add `sslmode=require`).
2. **Google Cloud** (after the billing approval, owner item o-36):
   - Create the project, link billing and set the ₹200 budget alert.
   - Enable Cloud Run, Cloud Build, Artifact Registry, Secret Manager and Cloud Scheduler.
   - Create the image repository: `gcloud artifacts repositories create empire --repository-format=docker --location=asia-south1`. Add a cleanup policy that keeps the last 5 images, because the free 0.5 GB fills with one image per release.
   - **Service accounts:**
     - Create a runtime account `empire-run` and give it `roles/secretmanager.secretAccessor` on these secrets only. Pass it as `--service-account empire-run@<project>.iam.gserviceaccount.com` to the service and to both jobs.
     - Give the build's service account `roles/artifactregistry.writer` and `roles/logging.logWriter`. New projects don't always grant these by default, and then `builds submit` fails.
   - Create one Secret Manager secret per "yes" row in §1.
     - **Cost:** Secret Manager's free tier is 6 active secret versions. Staging plus production need about 14, so expect well under ₹100 a month. That stays inside the ₹200 alert; tell management, because the approval sheet says ₹0.
3. **Build the image** (from the repository root, in Cloud Shell or with `gcloud` on the owner's computer):
   `gcloud builds submit apps/api --tag asia-south1-docker.pkg.dev/<project>/empire/empire-api:<git-sha>`
4. **Migrations job:**
   - **The jobs need the full production settings and secrets, the same as the service.** A Cloud Run job sets `CLOUD_RUN_JOB`, so the code refuses to start without `APP_ENV` and every required setting (D-052): `EDGE_PROXY_KEY`, `CLOUDINARY_URL`, `EMAIL_API_KEY`, `EMAIL_FROM`, `WEB_REVALIDATE_URL` and all the secrets.
   - `gcloud run jobs create empire-migrate --image … --command alembic --args upgrade,head --region asia-south1 --service-account empire-run@… --set-env-vars … --set-secrets …`, then `gcloud run jobs execute empire-migrate --region asia-south1 --wait`.
5. **The API service:**
   - `gcloud run deploy empire-api --image … --region asia-south1 --service-account empire-run@… --allow-unauthenticated --min-instances 0 --max-instances 3 --memory 512Mi --set-env-vars … --set-secrets …`.
   - Check `GET <service-url>/api/health/live` gives `{"status":"ok"}`, and `/api/health` gives 200 (database reachable).
   - Without the edge key, every other `/api/*` call must give 403. That is the edge guard (D-027).
6. **Background job** (Cloud Scheduler):
   - Schedule `empire-drain` every 15 minutes (`*/15 * * * *`, time zone Asia/Kolkata).
   - Method POST to `<service-url>/api/v1/internal/outbox/drain`, with the header `X-Internal-Key: <INTERNAL_API_KEY>`.
   - Retries: 0. The next run retries anything left.
   - The header is stored in plain text in the Scheduler job, and anyone with access to the project can read it. That's fine while only the owner has access. If access widens, rotate `INTERNAL_API_KEY` in the secret and the job together.
7. **Netlify:**
   - Create a site from the GitHub repo, with base directory empty and package directory `apps/web`.
   - Add the §1 variables with **All scopes**, then deploy. `API_ORIGIN` and `NEXT_PUBLIC_SENTRY_DSN` are read when the site is built, so after changing either, redeploy.
   - Staging domain: `staging.empirebuildcon.com`, a CNAME in Cloudflare set to DNS only. Keep it behind Netlify's password protection, or leave it unannounced; it is `noindex` either way.
8. **The owner's account:**
   - Create the job with the same settings as `empire-migrate`, then run it once: `gcloud run jobs create empire-admin --image … --command empire-api --args create-superadmin,--email,<owner@…>,--name,<name> --region asia-south1 --service-account empire-run@… --set-env-vars … --set-secrets …`, then `gcloud run jobs execute empire-admin --region asia-south1 --wait`.
   - It prints a setup link in the job's log, valid 24 hours and single-use. Use it at once: choose a password and turn on two-factor. Once used, the link is dead, even though the log keeps it for 30 days.
9. **Settings in the CMS:**
   - Settings → Lead routing → **Shared sales inbox** = `sales@empirebuildcon.com`. With it set, every new lead and site-visit request is emailed there (D-050).
   - Contact numbers, office address, social links.
   - Publish the approved consent text and legal pages (L6).

## 3. Staging checks (before production)

- [ ] **Client IP** (repeat after any change to Cloudflare's proxy, §4.4): sign in with a wrong password from two different networks (mobile data and Wi-Fi). Each network has its own limit; one network's lock-out must not block the other. In the API log, a request line's `client` must be the visitor's IP, not Netlify's. If `/api/*` answers 503 "Please try again in a minute", the client-IP header is wrong (D-052): fix `CLIENT_IP_SOURCE_HEADER`.
- [ ] **CSP:** a week of report-only on staging. Read `/_internal/csp-report` lines in the Netlify function log. Then set `CSP_ENFORCE=true` and test every page.
- [ ] **Media:** a real upload, confirm, delete and video poster on Cloudinary. Check whether a phone video's GPS metadata survives delivery. Also upload a photo of about **9.5 MB** through the CMS. Photos pass through the website's `/api` proxy, and Netlify functions have a request limit of about 6 MB. If it fails, send photos straight to Cloudinary as videos already are, or lower the photo cap.
- [ ] **Maps:** a real `maps.app.goo.gl` link resolves.
- [ ] **Email:** a test enquiry reaches `sales@`. A password reset email arrives. DKIM and DMARC pass (Gmail → "Show original").
- [ ] **Background work:** a scheduled offer starts within 15 minutes; the Scheduler job shows success.
- [ ] **Backup** (§6): one manual run and a restore into a scratch Neon branch.
- [ ] **Lighthouse and e2e:** the CI checks are green on the commit that's deployed.

## 4. Go-live checklist (owner approves each line)

1. Real content entered and checked against the content review (L5, L7). No sample data is published; production refuses it anyway.
2. Legal texts approved and published (L6).
3. §3 all ticked on staging; production set up the same way (§2).
4. **Cloudflare in front of the site** (D-052): the free rate-limiting rule for page requests per IP, for example 120 requests a minute to `/projects*`, `/properties*` and `/blog*`.
   - Decide this on staging. The rule needs the site proxied through Cloudflare (orange cloud) with SSL "Full (strict)". Netlify prefers DNS-only, so test both on staging and record the choice in DECISIONS.
   - **Proxying changes the client IP.** Behind Cloudflare, Netlify's `x-nf-client-connection-ip` is Cloudflare's address, so every visitor would share one rate limit. Switching to `cf-connecting-ip` is safe only if the site can't be reached without going through Cloudflare. Anyone can call `*.netlify.app` directly and set that header themselves. So proxy only with a way to block direct `*.netlify.app` traffic, and re-test the client-IP check in §3.
5. DNS: `empirebuildcon.com` and `www` point to Netlify. The 308 redirects for `.in`, `.co.in` and `www` stay (set up on 22 Oct).
6. `ALLOW_INDEXING=true` on the production Netlify site, then redeploy. Check `https://empirebuildcon.com/robots.txt` allows crawling and lists the sitemap.
7. Google Search Console: verify the domain (DNS TXT) and submit `https://empirebuildcon.com/sitemap.xml`.
8. UptimeRobot: `/` and `/api/health/live` every 5 minutes, alerting the owner.
9. Smoke test on production:
   - home and a project page with RERA, QR and up-rera.in;
   - an enquiry reaches `sales@`;
   - CMS sign-in with two-factor;
   - `robots.txt` and the sitemap.

## 5. Deploying a change

1. The pull request is merged with green CI, including the `image` job, which builds this same image.
2. Build the image tagged with the merge commit (§2.3). If the release has new migrations, run `empire-migrate` with that image first. The running API is still the old version for a minute, so a migration that removes or renames something the old code uses needs a two-step release; the pull request says so.
3. `gcloud run deploy empire-api --image …:<sha>` (keeps the settings). Netlify deploys the website by itself from `main`.
4. **Roll back:**
   - Cloud Run → Revisions → route 100% to the previous revision. Netlify → Deploys → "Publish deploy" on the previous one.
   - Migrations are reversible (CI checks `downgrade base`), but don't downgrade production without a backup taken first.

## 6. Backups and restore

- **Storage:** dumps count against GitHub's 500 MB of artifact storage on the free plan. After the first run, note the dump size here. If 30 days of dumps would pass about 400 MB, shorten `retention-days` or move the dumps to a Cloud Storage bucket.
- **The read-only role for backups** (Neon SQL editor, production): `CREATE ROLE backup WITH LOGIN PASSWORD '<long random>'; GRANT pg_read_all_data TO backup;`. Test it with the §3 backup run.
- **Daily:** `.github/workflows/backup.yml` dumps production (PostgreSQL 18 `pg_dump`, custom format), encrypts it with GPG (AES-256) and keeps it 30 days as a workflow artifact. It stays off until the owner adds the repository secrets `BACKUP_DATABASE_URL` (a **read-only** Neon role) and `BACKUP_PASSPHRASE`.
- **Neon** also keeps its own short restore window (point-in-time) on the free plan.
- **Restore** (into a scratch database first, never straight over production):
  1. Download the artifact, then: `gpg --batch --pinentry-mode loopback --passphrase-fd 3 --decrypt empire-<date>.dump.gpg > empire.dump 3<<<"$BACKUP_PASSPHRASE"`
  2. Create an empty Neon branch, then: `pg_restore --no-owner --no-privileges -d "<branch connection string>" empire.dump`
  3. Point a staging API at it and check the CMS: projects, leads and settings are there.
- **Keep `DATA_ENCRYPTION_KEY` with the backups' passphrase.** Staff two-factor secrets and recovery codes depend on it. A database restored without that key works, but every staff member must set two-factor up again. Lead data itself is not encrypted with it.
- **Restore drill, 6 Nov 2026 (L7a, local PostgreSQL 16, test data: 40 tables, 68 projects, 45 leads):**
  - the backup job's exact steps, run as a role with only `pg_read_all_data`: dump and encrypt took 3 s (190 KB);
  - decrypt and `pg_restore` into an empty database took 1 s, with no errors;
  - the row count of every table matched the source;
  - an API started on the restored copy answered `/api/health` ok, and its public project list was byte-for-byte the same as the source's.
  - Still to do at go-live: the same with production's PostgreSQL 18 (§3 checklist), and note the real dump size above.

## 6a. Load test (L7a, 6 Nov 2026)

Measured in the cloud workspace (2 CPUs, shared with the load generator), with one API process run like production (`--no-access-log --no-proxy-headers`) and `next start`, on local PostgreSQL 16 with 43 published projects. Production runs on different hardware, so read these as a floor and a shape, not a promise.

| What | At once | Requests in 20 s | Per second | p50 / p95 | Errors |
|---|---|---|---|---|---|
| Enquiry form (`POST /public/leads`), a different visitor each time | 10 | 953 | 47 | 191 / 374 ms | none |
| The same | 40 | 1,210 | 58 | 621 / 1,128 ms | none |
| One visitor, 8 enquiries | 1 | 8 | – | – | 5 accepted, then 429 (the limit, 5 per 10 minutes) |
| API project list (`/public/projects`) | 50 | 1,714 | 84 | 573 / 956 ms | none |
| Website project page (`/projects/<slug>`) | 50 | 1,416 | 70 | 683 / 991 ms | none |
| Website projects list (`/projects`) | 20 | 1,222 | 61 | 309 / 431 ms | none |

**Found and fixed: enquiries under load (D-054).** Before the fix, 10 enquiries at once made 9 of 42 fail after 30 s with a 500. Each request held its database connection and waited for a second one for the rate-limit counter, from the same pool. A launch-day ad could have done the same.

**After go-live,** repeat the enquiry row against staging with the real Cloud Run and Neon settings before any big campaign.

## 7. When something breaks

| Symptom | First look |
|---|---|
| Site shows errors on every page | Cloud Run logs (API down or database unreachable), Neon status; `/api/health` |
| `/api/*` answers 503 "Please try again in a minute" | The client-IP header (§3); Netlify function log line `[edge] no client IP` |
| CMS answers 403 everywhere | `EDGE_PROXY_KEY` differs between Netlify and Cloud Run |
| Leads aren't emailed | CMS Settings → Lead routing inbox; Resend dashboard; Scheduler job runs |
| Pages don't update after a CMS change | `WEB_REVALIDATE_URL` and `REVALIDATE_SECRET` on both sides; it updates within the cache time anyway |
| The API won't start: "APP_ENV must be staging or production" | `APP_ENV` missing on the Cloud Run service (D-052) |

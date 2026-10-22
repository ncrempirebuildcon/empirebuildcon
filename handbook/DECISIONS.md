# Decisions log: Empire website and CMS

One entry per decision. Newest at the bottom. Status is **Proposed**, **Accepted** or **Superseded**.
Never rewrite an accepted entry. Add a new entry that supersedes it and link back.

Live work plan: https://claude.ai/artifact/EkkY3MdhnYSe4gpceHgsY4

---

## Template

```
## D-000 · Title (Status, YYYY-MM-DD)
**Context:** what forced the decision.
**Options:** what was considered.
**Decision:** what we chose.
**Consequences:** what this makes easier or harder; what to watch.
**Verified / assumed:** facts checked (with date and source) vs. assumptions.
```

---

## D-001 · Where the project records live (Superseded by D-003, 2026-10-18)

**Context:** The brief asks for a live work-plan tracker, a decisions log and a handover doc, kept current at every phase.
**Decision:** Tracker as a live page both of us can update; decisions log and handover doc as files in `docs/`.
**Superseded:** D-003 keeps the tracker as is but makes `docs/` local-only.

## D-002 · Which RERA authority applies (Accepted, 2026-10-18)

**Context:** Owner confirmed projects start in Uttar Pradesh, and other states or cities may be added. The Panvel "Empire Buildcon" listing is a different company.
**Decision:** RERA authority, registration number, regulator URL and project QR code are stored **per project** (and per tower/phase when a phase has its own registration). Default authority: **UP-RERA**. Every project page and every ad/landing block shows the registration number, the regulator's website and the project QR code. Publishing a project is blocked until the number and QR are present.
**Consequences:** QR image is a required media role (`rera_qr`). A new state only needs a new authority value; MahaRERA's stricter layout rule (details in the top-right of ads) can be switched on per project if a Maharashtra project is ever added.
**Verified / assumed:** Verified 18 Oct 2026 from news reports, not the circulars: UP-RERA requires promoters to publish the project QR code in brochures and advertisements (The Week/PTI, 18 Jul 2024) and expects registration number, website link and QR code across all promotional material including digital and social (Storyboard18, 24 Jan 2025). The UP-RERA circular text itself is still to be read; re-check before Phase 5 templates are final.

## D-003 · Docs are local-only and git-ignored (Accepted, 2026-10-18; superseded in part by D-025)

**Context:** Owner instruction: every doc or `.md` file Claude makes goes in `A:\Adarsh\Empire_RealEstate\docs` and `docs/` is listed in `.gitignore`.
**Decision:** All project docs (brief, decisions, architecture, security, API design contract, handover, guides) live in `docs/`. The root `.gitignore` excludes `docs/`.
**Consequences:** Docs never reach GitHub, so they are not backed up by it and a developer who clones the repo won't see them. The owner should keep a backup of the folder (see owner actions). Files the build needs (the generated OpenAPI JSON for the typed client, code comments) are code, not docs, and stay in the repo.
**Verified / assumed:** n/a.

## D-004 · Business model and what "property" means (Accepted, 2026-10-18)

**Context:** Owner: Empire is a developer. The brief asks for property list/detail templates and a listings module "if wanted".
**Decision:** On the public site a **property is one configuration (floor-plan type) of a project**, e.g. "3 BHK, Tower B, 1,420 sq ft carpet". The property list searches configurations across projects by city, BHK, budget and type. The resale/rent `listings` module is **reserved in the design but not built**; flag `listings` stays off.
**Consequences:** Saves a whole module of work now. If resale/rent is wanted later, the table and endpoints are designed and can be built without touching projects.

## D-005 · No flat-level inventory in v1 (Accepted, 2026-10-18)

**Decision:** Availability is tracked per configuration (`available`, `sold_out`, `off_market`). The `unit` table is in the data model as future work behind flag `unit_inventory`.

## D-006 · Stack and versions (Accepted, 2026-10-18)

**Decision:** Stack from the brief (Next.js App Router + TypeScript + Tailwind; FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL; Cloudinary). Latest stable versions as checked today; exact versions pinned by lockfiles in Phase 3 and kept current by Renovate.

| Component | Version (checked 18 Oct 2026) | Note |
|---|---|---|
| Node.js | 24 LTS | Node 26 is expected to become LTS later in October; switch once the web host supports it (assumed from Node's usual schedule; nodejs.org could not be read) |
| pnpm | 12.14.0 | Workspace manager for the JS side |
| Next.js | 16.4.x (16.4.2 released 15 Oct 2026) | Requires Node ≥ 20.9 |
| React | 19.3.1 | |
| TypeScript | **6.0.3, not 7.0.2** | typescript-eslint 8.71.2 supports TypeScript < 6.1 only |
| Tailwind CSS | 4.3.3 | |
| next-intl | 4.14.9 | |
| Leaflet / react-leaflet | 1.9.4 / 5.0.0 | |
| Zod | 4.6.7 | Form validation in the web app |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 | Typed API client |
| Sentry (Next.js) | 11.8.0 | |
| ESLint / Prettier | 10.13.0 / 3.9.10 | |
| Playwright / @axe-core/playwright / Lighthouse CI | 1.64.1 / 4.14.0 / 0.15.1 | |
| Python | **3.14 (3.14.6)** | 3.15.0 shipped 9 Oct 2026 (PEP 790); wait until psycopg, pydantic-core and argon2 publish 3.15 wheels |
| uv | 0.13.1 | Python packaging and lockfile |
| FastAPI / Uvicorn | 0.143.3 / 0.54.0 | |
| SQLAlchemy / Alembic | 2.1.5 / 1.20.0 | |
| Pydantic / pydantic-settings | 2.14.1 / 2.16.0 | |
| psycopg | 3.3.6 | One driver for sync (Alembic) and async (API); works with poolers |
| PyJWT / argon2-cffi | 2.15.1 / 25.1.0 | |
| structlog / sentry-sdk | 26.1.0 / 2.72.0 | |
| pytest / httpx | 9.1.1 / 0.28.1 | |
| ruff / mypy | 0.17.1 / 2.4.0 | |
| pgvector (Python) | 0.5.1 | Extension enabled in the first migration |
| cloudinary (Python) | 1.46.3 | |
| PostgreSQL | Whatever the chosen host runs, 17 or 18 | Local and CI match the host's major version |

**Verified / assumed:** npm and PyPI versions read from the registries on 18 Oct 2026; Python schedule from PEP 790.

## D-007 · Hosting: free tiers first, with a costed go-live step-up list (Accepted, 2026-10-18)

**Context:** Owner: "use free first; if required, will purchase." The brief warns against free tiers that sleep or expire (Render's free API sleeps; its free database is deleted). Every fact below was read from the provider's own pages on 18 Oct 2026.

**Ruled out**

| Option | Why not |
|---|---|
| Vercel Hobby | Terms: "non-commercial personal use only"; they count "a paid employee or consultant writing the code" and "advertising the sale of a product or service" as commercial. Vercel Pro ($20/month) stays the preferred paid web host. |
| Render Free | API sleeps after 15 min idle and takes about a minute to wake; free Postgres is deleted after 30 days (+14 days grace); no free workers; docs say not for production. |
| Cloudflare Workers Free for Next.js | 10 ms CPU per request is too little for server rendering; OpenNext's docs still cite a 3 MiB compressed size cap on Free. (Workers Paid at $5/month is a possible paid option later.) |
| Koyeb, Railway free | Koyeb's free instance is 0.1 vCPU in Frankfurt/Washington, sleeps after 1 h and is no longer on its pricing page; Railway's free plan is $1/month of credit, too little to keep a service up. |
| Supabase Free | Pauses after a week of low activity. |

**Decision (development, staging and possibly launch)**

| Piece | Choice | Free allowance (verified) |
|---|---|---|
| Web app (Next.js) | **Netlify Free** | 300 credits/month, hard cap (production deploy 15, 1 GB bandwidth 20, 10k requests 2); commercial use not restricted; App Router, ISR and tag revalidation supported. If the cap is hit, **all sites on the account pause** until next month. |
| API and worker (FastAPI container) | **Google Cloud Run**, request-based billing, scale to zero | 2M requests, 180,000 vCPU-s, 360,000 GiB-s per month. Needs a Google Cloud billing account (card) even for the free tier. Cold start after idle: a few seconds (not the 1-minute Render wake). |
| Scheduler | **Cloud Scheduler** | 3 jobs per billing account free |
| Database | **Neon Free**, PostgreSQL 18 | 1 GB storage, 100 CU-hours/month per project, sleeps after 5 min and wakes in a few hundred ms, 6-hour restore window, pgvector, built-in pooling. Doesn't expire. |
| Daily backup | GitHub Actions job: encrypted `pg_dump`, kept 30 days | Within GitHub's free minutes for a private repo (to confirm when the repo exists) |
| Media | **Cloudinary Free** | 25 credits/month; 10 MB images and documents, 100 MB video; production use allowed |
| Email the system sends (lead alerts, resets) | **Resend Free** | 3,000/month, 100/day |
| Email to the company (`admin@`, `sales@`) | **Cloudflare Email Routing** → owner's Gmail | Free, unlimited forwarding. Real mailboxes (Zoho Mail Free or Google Workspace) can come later. |
| DNS, `.in`/`.co.in` redirects, holding page | **Cloudflare Free** | DNS; Single Redirects 10 rules per zone (needs the record proxied); Pages: static requests free and unlimited, apex custom domain needs the zone on Cloudflare |
| Errors | **Sentry Developer** | 5k errors, 1 user |
| Uptime | **UptimeRobot Free** | 50 monitors at 5 min; commercial use explicitly allowed |
| Redis | None (D-010) | — |

Expected monthly cost now: **₹0**, apart from small Google Cloud charges that may appear for network egress or image storage beyond free allowances (a ₹200 budget alert will be set).

**Design rules the free tiers force**

1. **Let the database sleep.** Uptime monitors check the home page and `/api/health/live` (no database). The event sweep runs every 15 minutes, not every minute. Time-critical deliveries (new-lead alert, cache revalidation after publish) are attempted inside the request right after the commit, with a 3-second budget; the sweep retries anything that failed. Neon compute is capped at 0.25–0.5 CU. Rough use: ~10 busy hours a day × 30 days × 0.25 CU ≈ 75 of the 100 CU-hours. A Settings warning shows when 80% is used.
2. **Spend Netlify credits on purpose.** No automatic deploys on every push; staging is deployed at milestones and before gates (~8–10 deploys a month ≈ 120–150 credits). `/api/*` uses a Netlify proxy rule (no function call) and the "no 3xx on `/api/*`" test runs against staging first thing.
3. **Put the API and database in the same region**, the closest one both providers offer to India (chosen when the accounts are created; Neon's region list decides).
4. **Cold starts are expected:** pages come from cache; server fetches time out at 3 s and the client refetches; the CMS shows a short "waking up" state.

**Go-live gate (Phase 9): risks of staying free, and the step-up for each**

| If we stay free | What can happen | Step-up (price verified 18 Oct 2026) |
|---|---|---|
| Netlify credits run out | Whole site paused until next month | Netlify Personal $9/month (1,000 credits), or move to Vercel Pro $20/month |
| Neon CU-hours run out | Database suspended: CMS and forms stop until next month | Neon Launch, pay-as-you-go, no minimum ($0.106 per CU-hour, $0.35 per GB-month) |
| Neon 6-hour restore window | Older mistakes recoverable only from the daily dump | Launch plan's longer window (exact length to check at Phase 9) |
| Cloud Run cold starts | First form submit or CMS load after idle waits a few seconds | Keep one instance warm (billed while idle; priced at Phase 9) |
| Resend 100/day | Alerts stop for the rest of that day | Resend Pro $20/month (50,000 emails) |
| Sentry one user | Only the owner sees errors | Team $26/month billed annually |

The owner decides at the Phase 9 gate. Claude's view: at minimum, budget the Netlify step-up and Neon pay-as-you-go before running ads, because those two can take the whole site down.

**Consequences:** The owner creates accounts at Netlify, Google Cloud (with billing), Neon, Cloudinary, Resend, Sentry and Cloudflare; the app code stays portable (a plain container and a plain Next.js app), so moving to Vercel Pro or Render later is configuration, not a rewrite.
**Verified / assumed:** Provider pricing, limits and terms pages read 18 Oct 2026 (sources listed in the Phase 1 report). Assumed: GitHub free Actions minutes cover the backup job; small Google Cloud egress/storage charges are possible.

## D-008 · Domains: apex canonical, DNS on Cloudflare (Accepted, 2026-10-18; status updated 2026-10-22)

**Context:** Owner accepted apex (may change later). Checked 18 Oct: `empirebuildcon.com` is registered at BigRock (created 23 Sep 2026, expires 23 Sep 2029) with Cloudflare nameservers (`kanye`, `susan`), but Cloudflare refuses queries for it (lame delegation), so `.com` does not resolve anywhere yet. `.in` and `.co.in` are delegated to BigRock nameservers and are present in the `.in` registry (a domain on serverHold drops out of it).
**Decision:** `https://empirebuildcon.com` is canonical. All three domains use **Cloudflare DNS (free)**. `www.empirebuildcon.com`, both `.in` forms and both `.co.in` forms send **308 to the same path and query on `https://empirebuildcon.com`**, set up on the web host where it supports redirect domains, otherwise with Cloudflare redirect rules. Canonical tags, sitemap and Open Graph URLs always use `.com`. Changing to `www` later is one setting plus redirects.
**Consequences:** Owner must activate the `.com` zone in Cloudflare (or fix the nameservers) and add `.in` / `.co.in` to Cloudflare. HTTPS must work on every variant; checked with `curl -I` in Phase 9.
**Verified / assumed:** RDAP for `.com` (Verisign) and DNS lookups through Google Public DNS, 18 Oct 2026. The `.in` registry's RDAP refused automated reading, so registrar details for `.in`/`.co.in` come from their nameservers only.
**Status 22 Oct 2026:** all three zones answer from Cloudflare (`.com` nameservers are now `keyla` and `amit`), the holding page is live on all three, and Cloudflare Email Routing MX records are in place for `.com`. Still to do by the owner: the 308 redirects for `.in`, `.co.in` and `www` (Cloudflare Bulk Redirects).

## D-009 · Authentication and sessions (Accepted, 2026-10-18)

**Decision:** Email + password, Argon2id; signed JWT in the `__Host-empire_session` cookie (HttpOnly, Secure, SameSite=Lax), backed by a `session` table so sign-out is immediate; CSRF token header on staff writes; lockout after 5 failures for 15 minutes; rate limits in PostgreSQL. One super-admin (`admin@empirebuildcon.com`) created by a one-time CLI setup link, then roles from the matrix in ARCHITECTURE.md §11. Optional TOTP two-factor for admins behind a flag.
**Consequences:** No tokens in browser storage. Details and tests in SECURITY.md.

## D-010 · Jobs, queue and rate limits in PostgreSQL; no Redis at launch (Accepted, 2026-10-18)

**Context:** The brief allows Redis or the database for rate limits and the job queue. The owner wants free tiers first, and every extra service is another account and another free tier to watch.
**Decision:** The **outbox table is the queue** (claimed with `FOR UPDATE SKIP LOCKED`) and **rate-limit counters are a PostgreSQL table**. The worker is one set of functions with two entry points: a long-running loop for paid always-on hosting, and `/api/v1/internal/outbox/drain` called by a scheduler on free hosting. The API also drains right after a request that wrote events, so lead alerts don't wait for the next tick.
**Consequences:** One less service. At our scale (hundreds of leads a month, a handful of staff) PostgreSQL handles this easily. Redis can be added behind the same interfaces if traffic ever needs it.

## D-011 · Media (Accepted, 2026-10-18)

**Decision:** Cloudinary, as in Current Investor: photos through the API with magic-byte and size checks and browser resizing; video and documents by signed direct upload with server-side verification of Cloudinary's signed reply. One `media` library table and a `media_link` table with one foreign key per owner type (exactly one set) holding role, order, cover and visibility.
**Consequences:** Owner turns on "Allow delivery of PDF and ZIP files" in the new Cloudinary account. Free-plan file limits re-checked when the account exists.

## D-012 · Maps (Accepted, 2026-10-18)

**Decision:** Pin taken from a Google Maps link (coordinates in URL, server-resolved `maps.app.goo.gl` short links, plus codes) or typed/dragged by staff. Shown with Leaflet + OpenStreetMap tiles, lazy-loaded, pop-up with project details and a Google Maps directions link. No Google Maps API key needed.
**Consequences:** If traffic grows, switch tiles to a provider with a usage plan (OpenStreetMap's public tiles have a fair-use policy).

## D-013 · Search (Accepted, 2026-10-18)

**Decision:** PostgreSQL full-text search + `pg_trgm` + structured filters; `pgvector` enabled from the first migration for Phase 7. No separate search service.

## D-014 · Languages (Accepted, 2026-10-18)

**Context:** Owner accepted the default: English first, ready for a second language; projects are in UP, so the second language is Hindi.
**Decision:** English in normal columns; a `translations` JSON overlay per row for other locales. `next-intl` with English at `/` and Hindi ready at `/hi/…`, off until Hindi content exists (flag `locale_hi`). Slugs stay English.

## D-015 · Sample data until real projects arrive (Accepted, 2026-10-18)

**Context:** Owner will send project details later and asked Claude to use samples or test data meanwhile. The brief requires honest content with no invented data on the live site.
**Decision:** A seed script creates **clearly fictional sample projects** (names like "Sample Project A", RERA numbers like `UPRERAPRJ-SAMPLE-01`, placeholder QR, generic renders marked "Sample image"). Every sample row has `is_sample = true`. In production: public endpoints never return sample rows, publishing a sample row is blocked, and the dashboard warns while any exist. The Phase 8 content review checks that none remain.
**Consequences:** The site and CMS can be built and tested end to end now; real content replaces samples through the CMS without code changes.

## D-016 · Leads: routing, alerts, CRM, site visits (Accepted, 2026-10-18)

**Context:** Owner accepted the defaults for questions 8–11.
**Decision:** New leads email a shared sales inbox; with more than one salesperson, leads are assigned in turn (round robin), configurable in Settings. No CRM at launch: the CMS pipeline is the CRM, with signed webhooks ready for Zoho, LeadSquared or others. WhatsApp click-to-chat at launch; WhatsApp lead alerts in Phase 6 (needs WhatsApp Business API). Site visits are requests for a preferred date and time of day; sales confirms by phone and records it in the calendar.

## D-017 · Legal text: Claude drafts, owner approves, no lawyer review (Accepted, 2026-10-18)

**Context:** Owner said lawyer review is not required.
**Decision:** Claude drafts the privacy policy, terms of use, disclaimer (RERA and "artist's impression" wording) and the lead-consent and cookie texts in plain language, marked "Draft" in the CMS until the owner approves them. The lead forms and consent records still work as designed, because the forms collect personal data either way.
**Consequences:** Claude is not a lawyer and the drafts are not legal advice; the owner accepts that risk. Go-live needs the owner's approval of the drafts instead of a lawyer's sign-off. A lawyer can review them later without code changes.

## D-018 · Optional pages are CMS pages that can be switched off (Accepted, 2026-10-18)

**Context:** Owner accepted the default page set but wants to remove or change pages later.
**Decision:** Blog/news, NRI, channel-partner enquiry and careers are CMS pages (and the blog a CMS section) that staff can edit, unpublish or remove from the menu. Unpublished pages return 404 and drop out of the sitemap.

## D-019 · How development happens (Accepted, 2026-10-18; superseded in part by D-026)

**Context:** The code lives in `A:\Adarsh\Empire_RealEstate` on the owner's computer. Claude works from a cloud workspace and can reach that folder through the desktop app link (a Linux shell with git 2.34, Node 22, Python 3.10; no Docker).
**Decision:** Claude builds and tests in the cloud workspace (full toolchain, PostgreSQL), then writes the files into the owner's folder and makes the git commit there. The owner pushes to GitHub. A `docker-compose.yml` for PostgreSQL is still provided for any future developer. Git in the owner's folder needs permission to delete its own lock files, so Claude will ask for delete permission on that folder at the start of Phase 3.
**Consequences:** The owner does not need to install anything to follow progress; previews come from the web host's preview deployments.

## D-020 · API contract (Accepted, 2026-10-18)

**Decision:** `handbook/api/openapi-v1.yaml` (OpenAPI 3.1, 159 operations) is the agreed design. From Phase 3 the FastAPI code is the source of truth and generates the live spec; CI generates the typed TypeScript client from it and fails if the client is stale. Differences from the design are recorded here.

## D-021 · Logo kit is a faithful vector redraw (Accepted, 2026-10-18)

**Context:** No vector or designer file exists; owner wants Claude to make one that looks the same.
**Decision:** In Phase 2 Claude redraws the logo as clean vector artwork matching the original's layout: the arched ring, four rising towers, palms, the EMPIRE™ wordmark in a classical serif, "Delivering Happiness", and the four-point star rule. Flat gold, single-colour gold, bronze and white versions; a horizontal header lock-up; a towers/"E" mark for favicon and app icon. The photo-style render stays available for large hero use where it looks good.
**Consequences:** Owner approves the redraw at the Phase 2 gate. The exact lettering will be close but not identical, since the original typeface is unknown.

## D-022 · Phase 2 sample templates for management review (Proposed, 2026-10-18)

**Context:** Owner asked for sample UI/UX templates, backed by research, to get approval from Empire's management.
**Decision (proposed):** One design canvas ("Empire Website Templates") with two home-page options (A "Ivory Arch", B "Full-bleed Gallery"), a brand kit board with the draft vector logo, and the projects list, project detail, contact, three mobile screens and two CMS screens in Option A's style. The page patterns (key-facts strip with RERA + QR, two-field form with separate consent, no pop-ups, dated progress, sticky mobile bar) apply to whichever home option is chosen. Research basis: DESIGN_RESEARCH.md (owner's private docs).
**Consequences:** Management picks A or B and comments on the logo; the remaining templates (property detail, about/track record, blog, campaign page, legal, 404, other CMS screens) follow in the chosen style before the Phase 2 gate.
**Verified / assumed:** Images on the canvas are sample illustrations made for the review, not photos; real photography replaces them. All projects, prices, RERA numbers and people are samples.

## D-023 · Black & gold theme added as a second design direction (Accepted, 2026-10-20)

**Context:** The client asked for templates in black and gold, the colours the original logo uses (gold artwork on a dark ground).
**Decision:** Accepted by the owner on 20 Oct 2026: Black & gold is the website theme. The same design canvas gets a second page, "Black & gold (dark)", and opens on it. It holds six boards: Home, Brand kit, Projects list, Project detail, Mobile home and Mobile project. The page patterns are the same as the light set (RERA + QR strip, carpet area in sq ft and sq m, open prices, two-field form with separate consent, no pop-ups, dated tower progress, sticky Call · WhatsApp · Enquire bar). Palette: warm near-black `#0E0C0A` page, `#171411` cards, ivory `#F5EEDF` headings, `#D9CFBF` body text, metallic gold gradient for the logo and big headings, gold `#D9A441` buttons with black text. A metallic-gold vector logo set (stacked, horizontal, mark) was drawn for dark backgrounds. The light "Ivory & gold" set stays on its own page for comparison.
**Consequences:** Management picks Ivory & gold or Black & gold (and Option A or B for the home layout if light). Whichever is chosen becomes the design tokens in Phase 3; the build supports one theme at launch, and a light/dark switch could be added later at extra cost.
**Verified / assumed:** Contrast checked against WCAG AA on `#0E0C0A`: headings 16.9:1, body 12.7:1, muted 7.1:1, gold 8.7:1, black on gold buttons 8.7:1. QR codes and floor plans sit on an ivory tile so phones can scan them and plans stay readable. A dark site needs good dusk or night photography; daytime photos look flat on black. Night images on the canvas are sample illustrations.

## D-024 · Remaining Phase 2 templates, all in Black & gold; CMS uses the same theme (Accepted, 2026-10-20)

**Context:** With the theme approved, the templates still missing from Phase 2 (brief §9, Phase 2 steps 2–5) can be made.
**Decision:** All remaining templates are made in Black & gold on the same canvas. Public pages go on the "Black & gold (dark)" page: Contact, mobile enquiry flow, About, 404, Properties list and detail (desktop and mobile), Blog list and article, Legal (privacy policy as the model), Campaign landing page (desktop and mobile), and a components-and-states board. CMS screens go on a new "Black & gold — CMS" page: sign-in, dashboard, leads pipeline, lead detail, site-visit calendar, project editor with the media manager, page/block editor, offers and blog, users and roles, settings and integrations (including SEO and feature flags), audit log. The CMS uses the same tokens as the website, with denser 14 px tables, so there is one token set to build and maintain. Design tokens, type scale, spacing, radii and component rules are written down in `DESIGN_SYSTEM.md`.
**Consequences:** The light "Ivory & gold" boards stay on the canvas for reference only; they are not built. Brief §7 colour tokens are replaced by the Black & gold tokens in `DESIGN_SYSTEM.md`. The Phase 2 gate is the owner's approval of the full Black & gold set.

## D-025 · Developer handbook in the repo; owner's notes stay private (Accepted, 2026-10-20)

**Context:** The owner wants any other developer (or Claude in a later session) to be able to understand the work, pull it, change it and add to it. D-003 kept every doc out of git, so a developer cloning the repo would see none of the architecture, decisions or design rules.
**Decision:** Technical docs live in `handbook/` and are committed: README (start here), CONTRIBUTING (git, push/pull and review rules), CODE_STYLE (code and comment rules), SETUP, ARCHITECTURE, SECURITY, DECISIONS (this log), DESIGN_SYSTEM, `api/` and `diagrams/`. `docs/` keeps only the owner's private material (project brief, handover with accounts and owner actions, design research) and stays git-ignored. Root files for every contributor: `README.md`, `AGENTS.md` (rules for AI coding agents, imported by `CLAUDE.md`), `.editorconfig`, `.gitattributes`, `.github/pull_request_template.md`.
**Git workflow:** `main` is protected and always deployable; all work happens on short-lived branches and reaches `main` only through a reviewed pull request with green CI (squash merge). Details in `handbook/CONTRIBUTING.md`. Claude follows the same rules; until the owner says otherwise, Claude commits on a branch and the owner pushes (brief §10), and Claude never pushes to `main` or merges its own pull request.
**Consequences:** Every change that alters behaviour updates the matching handbook page in the same pull request. Complex code carries the comment tags from `handbook/CODE_STYLE.md` (`WHY`, `INVARIANT`, `DO NOT CHANGE`, `COMPLIANCE`, `SECURITY`), so a newcomer knows what must not be changed and why. The repository must stay private, since the handbook names the owner's accounts and business rules.

## D-026 · Phase 3 working setup: GitHub is the source of truth, Claude pushes its own branches (Accepted, 2026-10-22)

**Context:** The owner approved the designs and the gold logo (Phase 2 gate, 22 Oct 2026), created the GitHub, Netlify, Google Cloud, Neon and Sentry accounts, and allowed Claude to push its own branches and open pull requests. D-019 had Claude committing inside the owner's folder with the owner pushing.
**Decision:**
- The private GitHub repository is the source of truth. Claude works in a clone in its cloud workspace, pushes feature branches and opens pull requests; the owner (or a reviewer) merges. `main` is protected (PR, one approval, green CI, no force pushes).
- One-time exception: the first commit (handbook and brand files only, no code) was pushed to `main` so that pull requests have a base.
- The owner's folder `A:\Adarsh\Empire_RealEstate` keeps `docs/` (private). The owner can clone the repo there with GitHub Desktop. Until then Claude also copies the files there as a backup.
- The background worker is the `empire-worker` entry point of the API package, not a separate `apps/worker` folder; one codebase, two entry points (D-010).
- pgvector is created by the first migration wherever the server has it (Neon, CI, the Docker image), so a bare local PostgreSQL still works until Phase 7.
- Fonts are self-hosted from npm (`@fontsource`), so pages make no Google Fonts requests: simpler CSP and no visitor data sent to Google.
- The nonce-based Content-Security-Policy arrives with the public pages in Phase 5; the other security headers ship in Phase 3.
- Dependabot (built into GitHub) opens dependency updates instead of Renovate, so no extra app needs installing.
**Verified / assumed:** Versions re-read from npm and PyPI on 22 Oct 2026. Changes since D-006: FastAPI 0.159.1, SQLAlchemy 2.1.6, Alembic 1.20.1, pydantic-settings 2.16.1, sentry-sdk 2.73.0, typescript-eslint 8.72.0 (still requires TypeScript < 6.1, so TypeScript stays 6.0.3), uv 0.13.5. GitHub Action majors read from their tags: checkout v7, setup-node v7, pnpm/action-setup v6, setup-uv v10, gitleaks-action v3, upload-artifact v7. The `pgvector/pgvector:pg18` image tag is listed in pgvector's README.

## D-027 · Security review fixes before the first pull request (Accepted, 2026-10-22)

**Context:** An independent review of the Phase 3 code (sessions, CSRF, brute force, permissions, tokens, errors, web) found issues that the tests didn't cover. None had reached any server.
**Decision:**
- **Edge key and client IP.** Only our web proxy may call the API. The proxy adds `X-Empire-Edge-Key` (`EDGE_PROXY_KEY`, required in staging and production) and `X-Empire-Client-IP` (taken from the host's header, `CLIENT_IP_SOURCE_HEADER`), after stripping any `X-Empire-*` header the visitor sent. The API refuses calls without the key (403), except health checks and internal scheduler calls, and never reads `X-Forwarded-For`. `/api/v1/internal/*` answers 404 on the website. This replaces the "trusted proxy hops" setting, which couldn't be right on Cloud Run.
- **Lockout.** Every attempt is counted per account and network before the password is checked: no parallel guessing past 5, no locking the owner out from another network, and identical answers for unknown and real emails. `failed_login_count` is removed; `locked_until` stays only as a CMS note.
- **Errors and reports.** Sentry runs with `include_local_variables=False` and password fields are hidden from `repr`. Unexpected errors are caught inside the middleware stack, so 500s keep the security headers, `no-store` and the request id.
- **Accounts and permissions.** Reset links are claimed atomically, and every other open link is burned on reset or password change. The last *usable* super-admin can't be demoted or deactivated (rows locked). Phones are masked in audit diffs. `staff()` both marks and enforces a permission. Only a super-admin can switch `admin_2fa`. The raw-HTML lint ban now also covers components and the UI package.
**Consequences:** The deploy (Phase 9) sets the same `EDGE_PROXY_KEY` on Netlify and Cloud Run and confirms the client-IP header on Netlify staging. The nonce-based CSP stays in Phase 5 (D-026).


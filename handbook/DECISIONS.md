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

## D-026 · Phase 3 working setup: GitHub is the source of truth, Claude pushes its own branches (Accepted, 2026-10-22; who pushes superseded by D-029)

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


## D-028 · Protecting `main` depends on the GitHub plan (Accepted, 2026-10-22)

**Context:** D-026 assumes a protected `main` (PR, one approval, green CI, no force pushes). The repository is private, and the owner's GitHub account is on the free plan.
**Options:**
1. Stay on GitHub Free and follow the rules by hand. Costs nothing, but GitHub doesn't stop a direct push to `main`.
2. GitHub Pro on the owner's personal account. Protection is enforced on private repos.
3. A GitHub organisation on GitHub Team. Protection is enforced, and seats suit more developers later.
4. Make the repo public. Protection is free, but the code becomes public. Not wanted.
**Decision:** The owner chose option 1 on 22 Oct 2026; a paid plan needs management approval. Stay on Free until a second developer joins or the Phase 9 go-live gate, whichever comes first; then the owner picks 2 or 3. Claude doesn't push to `main` either way (D-026), so the risk until then is mostly human error. The settings to apply are listed in CONTRIBUTING §12.
**Consequences:** Until the upgrade, the owner checks that CI is green before merging. The CI workflow already runs on every pull request.
**Verified / assumed:**
- Checked 22 Oct 2026 in GitHub Docs ("About protected branches", "GitHub's plans") and on github.com/pricing:
  - Protected branches on private repos need Pro, Team or Enterprise.
  - The Free plan lists repository rules for public repos only.
  - Free includes 2,000 Actions minutes a month; Pro and Team include 3,000.
  - Team costs $4 USD per user per month for the first 12 months.
- The Pro price wasn't shown on the pages read.

## D-029 · The owner pushes; Claude has no GitHub access (Accepted, 2026-10-22)

**Context:** D-026 had Claude pushing its own branches through the GitHub account connected to Claude. The owner created the repository `ncrempirebuildcon/empirebuildcon` and decided not to give that account access.
**Decision:**
- This goes back to the D-019 flow:
  - Claude builds and tests in its cloud workspace.
  - Claude then commits on a feature branch in the owner's working copy, `A:\Adarsh\Empire_RealEstate`. That folder is now a git repository whose `origin` is the GitHub repository.
  - The owner pushes with the Empire GitHub account, opens the pull request and merges.
- The owner pushes the one-time bootstrap commit on `main` first, so GitHub makes `main` the default branch.
- The rest of D-026 stands: the worker entry point, conditional pgvector, self-hosted fonts, the CSP in Phase 5, Dependabot and the versions.
**Consequences:**
- Claude can't see CI results or review comments on GitHub. When CI fails, the owner shares the failing job's log or a screenshot.
- Pull request auto-fix isn't available.
- Before new work, the owner fetches `origin`, so Claude starts from the latest `main`.

## D-030 · Fixes after the first CI run on GitHub (Accepted, 2026-10-22)

**Context:** The first run of the CI workflow on pull request #1 failed in two places:
- The `api` and `contract` jobs failed with "Unable to resolve action `astral-sh/setup-uv@v10`, unable to find version `v10`". D-026 assumed a moving `v10` tag, but setup-uv publishes only full version tags.
- The `secrets` job failed with 403 "Resource not accessible by integration". On pull requests, gitleaks-action reads the PR's commits through the API, which needs `pull-requests: read`.

The `web` job passed.
**Decision:**
- setup-uv is pinned to the commit of release v10.3.2 (`07a047e…`), with the version in a comment. That release includes the checksums for uv 0.13.5. Dependabot updates the pin.
- The `secrets` job gets `pull-requests: read`. PR comments are turned off, so the token stays read-only.
- gitleaks is pinned to 8.28.0, the version used for the local scans. The action's own default is 8.24.3.
**Verified / assumed:** Checked 22 Oct 2026:
- The setup-uv releases page lists v10.3.2 (22 Oct) at commit `07a047e608db84b3d8c06cd9a7c7dcc9c355c18e`, "update known checksums for 0.13.5". Its README pins by SHA.
- The 403 response named the needed permission (`x-accepted-github-permissions: pull_requests=read`).
- gitleaks-action's README lists `GITLEAKS_ENABLE_COMMENTS` and `GITLEAKS_VERSION`.

## D-031 · Phase 4 part 1: projects and catalogue in the CMS (Accepted, 2026-10-22)

**Context:** Phase 4 (CMS core) is delivered in five pull requests:
1. Projects and catalogue.
2. Media.
3. Leads.
4. Content and SEO.
5. Settings, users and email.

Building part 1 against the design contract (D-020) needed some choices the contract doesn't make.
**Decision:**
- **Contract additions (no renames).** All 52 Projects and Catalogue operations keep their method, path, operationId and permission, and a test enforces this.
  - `PATCH /admin/projects/{id}` takes `ProjectUpdate`, in which every field is optional. `publish_state: archived` archives the project and `draft` restores it. `published` is refused, because publishing goes through `…/publish`.
  - List rows are `ProjectAdminSummary`.
  - New fields:
    - `rera_account` (bank name, account name, account number), which the approved design shows in the RERA section.
    - `featured_order` on `ProjectAdmin`.
    - `pin_source` on `LocationInput`.
    - `sort_order` on construction updates and payment plans.
    - `project_count` on localities.
  - `MapsResolveRequest.input` allows 2,048 characters, because real Google Maps place links run past 500.
  - `MapsResolveResult.plus_code` returns the normalised plus code, so the project stores only the code and never the place name typed after it.
- **Publish blockers** are computed by one function:
  - RERA number missing;
  - RERA QR code missing (always shown until the media manager arrives in part 2);
  - no configuration;
  - sample data in production.
- **Lifecycle:**
  - Only drafts that were never published can be deleted. `published_at` is never cleared, so it records this.
  - Archiving, or putting a live project back to draft, needs `projects.publish`. So does setting a live project's sales status to or from "off market", because that also hides it from the website. A configuration's own off-market status is ordinary sales work and needs only `projects.write`.
  - Archiving a live project emits `project.unpublished`.
  - `construction_update.published` fires only for live projects.
  - Other child edits on a live project emit `project.updated`.
- **Data:**
  - Payment plan stages are a validated JSON array on the plan, not a separate table. They are always read and written with their plan, and the "stages total exactly 100%" rule needs the whole list.
  - A database constraint keeps a project's locality inside its city.
  - Area is stored in square metres with 2 decimals.
- **Duplicate:** the copy is a draft named "(copy)". It does not carry the original's RERA registration: the project's and each tower/phase's registration number, the RERA link, the designated account and the SEO canonical path are cleared, because a copy must never go live under another project's registration.
- **Plus codes:** decoded by our own small port of Open Location Code, tested against Google's official vectors. Short plus codes are refused.
- **Map links:** coordinates are also read from `/maps/search/<lat>,<lng>` and `/maps/place/<lat>,<lng>`, the form a shared "dropped pin" usually redirects to.
- **Maps resolver limits:** the SSRF limits are in SECURITY.md §5.
- **Displayed prices and areas:** the API computes `display` with a Python twin of `packages/ui/src/format`. Both are tested with the same vectors, so the CMS preview and the API always agree.
- **Units and listings:** still not built (D-004, D-005).
**Verified / assumed:**
- PyPI, checked 22 Oct 2026:
  - `openlocationcode` 1.0.1 was last released on 20 Jul 2019, as a source package only.
  - `pluscodes` 2022.1.3 was released on 27 Aug 2022.
  - `httpx` 0.28.1 is the latest stable release. It moved from dev to main dependencies for the resolver.
- The resolver hasn't been tried against a real `maps.app.goo.gl` link, because tests never use the network. Try one on staging in Phase 9.

## D-032 · Hold TypeScript at 6.0 and the Node types at 24 (Accepted, 2026-10-22)

**Context:** Dependabot opened two pull requests on 22 Oct 2026:
- TypeScript 6.0.3 → 7.0.2 (PR #3). Its CI failed in two jobs:
  - `web`: typescript-eslint 8.72 stops with "typescript-eslint does not support TS 7.0".
  - `contract`: openapi-typescript 7.13 crashes on TypeScript 7 ("Cannot read properties of undefined (reading 'createKeywordTypeNode')").
- `@types/node` 24 → 26. That would describe a Node version we don't run; `.nvmrc` pins Node 24.
**Decision:**
- Dependabot ignores TypeScript major and minor updates (patches still come) and `@types/node` major updates. The ignore rules and their reasons are in `.github/dependabot.yml`.
- The owner closes both pull requests with the comment `@dependabot ignore this major version`.
**Consequences:** We revisit TypeScript when typescript-eslint and openapi-typescript both support the newer version. The Node types move together with a Node upgrade.
**Verified / assumed:** The failures were read from the CI logs of PR #3 on 22 Oct 2026. The other jobs passed (API 96 tests, secret scan). Ignore syntax and comment commands are as described in GitHub Docs ("Dependabot options reference" and "Dependabot pull request comment commands"), checked 22 Oct 2026.

## D-033 · Phase 4 part 2: media manager (Accepted, 2026-10-23)

**Context:** Part 2 adds photos, videos, documents, the RERA QR, brochures, floor plans, progress photos and share images. It uses Cloudinary (D-007), but no account credentials exist in the development workspace.
**Decision:**
- **Two stores behind one interface.**
  - `CloudinaryStore` uses the official `cloudinary` SDK, wrapped and typed, with credentials passed on every call.
  - `FakeStore` runs development, tests and the browser suite with no network. It mimics Cloudinary's signed direct upload and signed replies.
  - Staging and production refuse to start with the fake store or without `CLOUDINARY_URL`.
- **Signing.**
  - Requests are signed with SHA-256; replies are accepted with SHA-1 or SHA-256.
  - Each direct upload gets an `upload_intent`: one user, one use, 60 minutes (Cloudinary's own signature lifetime, so a 100 MB video on a slow line still fits), `overwrite=false`.
  - The API re-reads the asset from the Admin API before saving.
- **Storage layout.**
  - Public ids are `folder` + uuid, which behaves the same in Cloudinary's fixed and dynamic folder modes.
  - PDFs are stored as images, so they open in the browser and get a page-1 thumbnail. Office files are stored as raw files and keep their extension.
  - Videos get an eager poster, because the Free plan transforms only 40 MB of video on the fly.
- **Privacy.**
  - Photo metadata (EXIF/GPS, XMP, IPTC, comments) is stripped on the server before upload, so even the stored original has no location data. Anything appended after the image's real end is cut off. The ICC colour profile is kept. Animated images are refused, because re-encoding would silently keep one frame.
  - Start-up configuration errors never echo environment values (`hide_input_in_errors`).
  - Video container metadata (phones can record GPS) is still delivered as uploaded. This is checked on staging in Phase 9.
- **Rules.**
  - Single-valued roles replace the previous item.
  - The cover is the pinned item, or else the first visible one.
  - A live project's RERA QR can't be hidden or removed; it can only be replaced.
  - A duplicate copies no media links and clears the share image, so a copy can never carry the original's QR (COMPLIANCE).
  - Floor-plan changes emit `configuration.changed`.
  - A new event, `media.upload_discarded`, routes every destroy through the outbox.
- **Honest labels.**
  - A photo is labelled artist's impression, actual photo, or progress photo with its month.
  - The month can't be in the future (IST).
  - Documents carry no label.
  - The API enforces it: a gallery photo (project or construction update) or hero image can't be shown on the website without a label. Unlabelled photos attach hidden. Sample media is exempt, because it is never public.
  - The CMS asks for the label before a batch of photos uploads.
  - Construction updates can't be dated in the future.
- **Roles not used yet:** `hero` and `og_image` links are refused for now. The share image is `seo.og_image_id`; the hero role waits for the Phase 5 design.
- **CMS:**
  - Media actions need `media.upload`. Deleting from the library needs `media.manage`, and only unattached files can be deleted.
  - Uploads run one at a time, with progress and Cancel.
  - A file's title, alt text and label are edited in one dialog with a single Save.
  - The share image is `seo.og_image_id`, saved with the project.
  - Progress photos are labelled "progress photo" with their update's month automatically.
- **Contract additions:**
  - `Media`: `label`, `label_month`, `is_sample`, `attached_count`.
  - `UploadSignature`: `fields`, `expires_at`, and `resource_type: image` for PDFs.
  - `ProjectAdmin.og_image`.
  - `unattached=true` on the media list.
**Verified / assumed:**
- **Cloudinary documentation, read on 23 Oct 2026:**
  - authentication and response signatures;
  - upload reference and folder modes;
  - Admin API resource lookup;
  - transformation reference;
  - video posters;
  - PDF delivery;
  - pricing.
- **Free plan limits** (checked the same day): 10 MB images and raw files, 100 MB video, 25 MP, Admin API 500 requests per hour, 40 MB on-the-fly video.
- **The response-signature example in Cloudinary's docs is inconsistent.** Its printed hex doesn't match the string shown. We follow the documented recipe, cross-checked against the vectors in Cloudinary's own SDK tests.
- **PyPI versions** (checked 23 Oct 2026):
  - `cloudinary` 1.46.3, released 4 Oct 2026.
  - `pillow` 13.0.0, released 16 Oct 2026.
  - `python-multipart` 0.0.32.
- **Not yet tried against a real account.** Try a real upload, confirm, delete and poster on staging. The owner must enable PDF delivery in the Cloudinary console.
- **Phase 5 CSP must allow:** `connect-src https://api.cloudinary.com` and `img-src https://res.cloudinary.com`.

## D-034 · Phase 4 part 3: leads, site visits and dashboard (Accepted, 2026-10-23)

**Context:** Part 3 builds the lead pipeline, the public lead intake API, site visits, the dashboard and consent texts. The public forms come in Phase 5, and email alerts in part 5.
**Decision:**
- **Phone rule (strict, our own code rather than `phonenumbers`):**
  - Mobiles are 10 digits starting 6–9.
  - Landlines must include the STD code.
  - Foreign numbers are refused for now; NRI leads come in Phase 6.
  - "Fancy" numbers (repeated digits, runs such as 98765 43210) are deliberately accepted, because operators sell them as VIP numbers. Rate limits, the honeypot, duplicate linking and "mark spam" handle junk.
  - Landlines with STD codes starting 6–8 can't be told from mobiles, so they may get a WhatsApp link.
  - Sample leads use `+91 00000 000NN`. No Indian number starts with the trunk prefix 0, so these can't belong to anyone, and the public forms refuse them.
- **Consent:**
  - Consent texts are versioned and never edited after publishing.
  - A draft-marked text can't be published in production. Until one is published, public intake answers 503.
  - Marketing consent is a separate optional record.
- **Rate limits:** IPv6 visitors are keyed by their /64 network, and IPv4-mapped addresses by their IPv4. This covers intake, sign-in, lockout and password-reset requests, so rotating addresses inside one allocation doesn't help.
- **Spam and duplicates:**
  - A filled honeypot gets an identical 201 with a look-alike reference, and nothing is stored.
  - Duplicates (same phone and project within 24 hours) are saved, linked, given to the same owner, and emit `lead.created` with `alert: false`.
- **Assignment:**
  - Round robin keeps its turn in a settings row locked until commit. That makes it fair under concurrent submissions; a test runs 12 at once across 3 people.
  - Manual leads default to the person entering them. Giving one to someone else needs `leads.assign`.
- **Access:**
  - Object-level rule: anyone else's lead answers 404.
  - Duplicate links are scoped too: a viewer never learns that a lead they can't see exists.
  - A manual lead links only to an earlier lead its creator can see.
  - Search text is never written to the audit log, only a marker.
  - Site visits follow their lead's rule, because a visit shows the buyer's details.
  - The UTM report is counts only. Sales see their own leads; marketing (no `leads.read`) sees counts for all.
- **Export:**
  - At most 50,000 rows. A bigger request is refused, never cut off silently.
  - The export needs the `X-CSRF-Token` header and refuses cross-site fetch metadata, so another site can't trigger a download. The CMS downloads it with fetch.
  - Formula-guarded CSV with a BOM. Audited, with a timeline line per exported lead.
- **Erasure and retention:**
  - Erasure also scrubs notes, the preferred contact time, the visitor-typed UTM term and content, the lost-reason note, visit notes, the IP hash, the consent page URL and stored event payloads that carry personal data.
  - It covers the lead's whole duplicate group. With `?scope=person` it also covers every lead with the same phone; the dialog offers that.
  - Lost reasons are a fixed code plus an optional note (`other` requires one), so reports keep the code after the note is erased.
  - Audit rows are never edited (an invariant of the audit log), so personal free text never enters them: notes and emails are recorded as `[hidden]`.
  - Retention anonymises after 3 years without real activity; reads and exports don't count.
  - Visitor enquiries and read/unread write no audit rows; the lead's timeline covers them.
- **Brochure requests** return the public file URL with `expires_at: null`. Gating collects a lead; it isn't access control, and the docs say so.
- **CMS:**
  - Lists, cards and the dashboard show masked phone numbers. The full number shows only on the lead detail and in its call/WhatsApp links. Browser titles never carry the buyer's name.
  - Stage moves use an accessible "Move to" control; lost needs a reason code, plus a note when the code is "other".
  - Confirming a visit moves its lead to "site visit". Later edits to a confirmed visit (time, notes, handler) don't move the lead again.
  - Calendar times are typed and shown in IST and sent as UTC.
  - Dashboard links appear only for CMS screens that exist.
  - `next dev` is told not to write its own `apps/web/AGENTS.md` (`agentRules: false`); the root AGENTS.md is the single place for AI rules.
- **Not built yet:**
  - Staff-created site visits.
  - Recording a consent withdrawal.
  - Foreign numbers.
  - An event for detail edits.
  - Email alerts (part 5).
- **Contract changes:**
  - Additions: `marketing_consent`, `GET /admin/lead-owners`, inbox `status_counts`, `lost_reason_note`, `same_phone_count` (shown only to `leads.erase` holders), extra lead/visit/dashboard fields, and the `privacy` settings group.
  - New query parameters: `open`, `utm_source` and `utm_medium` (inbox and export), `scope` (erase), `open` (site visits) and `blocked` (projects list).
  - Tightened: `lost_reason` is a code list instead of free text, and `preferred_bhk` is 0.5–20 in half steps.
  - Deviations: `is_sample` instead of `is_test`, a nullable `page_url` for manual leads, typed enums, and the honeypot and `website` rules above.
**Verified / assumed:**
- **Indian numbering**, read 23 Oct 2026:
  - DoT National Numbering Plan 2003 (§1.9, §2.1.5–2.1.6, Annex I);
  - TRAI recommendations of 29 May 2020;
  - TRAI press release 09/2025 (still a recommendation; numbers stay 10 digits).
- **`phonenumbers`** 9.0.41 (PyPI, 8 Oct 2026) was considered and not added.
- **Export timing:** 50,000 rows streamed in about 6 s locally.

## D-035 · Phase 4 part 4: content and SEO (Accepted, 2026-10-24)

**Context:** Part 4 builds pages with blocks, blog posts, FAQs, offers, testimonials, redirects and SEO checks in the CMS. The public pages, public content endpoints, the sitemap and redirect hit counting come in Phase 5.
**Decision:**
- **Blocks:**
  - 17 block types, each a strict data shape. `Block` and `BlockInput` are discriminated unions on `type` instead of the contract's free `data` object; every variant keeps the contract's fields, and a test enforces it.
  - No text accepts HTML. Links are a site path or `https://`; videos are YouTube/Vimeo, stored as provider plus id.
  - Stats need a source and an as-of date that isn't in the future (honest numbers).
  - Block files and post covers are `media_link` rows with internal-only roles `block` and `cover`, kept in step by the content API; the media-links endpoints refuse to change them. Offer images and testimonial photos are restrictive foreign keys.
  - Photos in hero, image and gallery blocks, post covers and offer images need an honest label (extends D-033; covers and offer images were added after review, because they often show renders). Testimonial photos don't: they show a person, not a property.
- **Permissions (ARCHITECTURE §11):**
  - Setting a schedule, or archiving or un-drafting a live page or post, needs `content.publish`.
  - Changing `seo` on pages and posts needs `seo.manage`. Projects don't check it, but every role with `projects.write` holds it.
  - FAQs: showing one needs `content.publish` (§11 lists FAQs under publish); editing a shown FAQ's text needs only `content.write`.
  - Testimonials need `content.publish` for every write, as in the contract.
- **Legal pages (D-017):**
  - `legal.publish` is needed to publish, unpublish, schedule, archive, restore or delete a legal page, to edit one while it's live or scheduled (so the wording the schedule tick publishes is what a `legal.publish` holder scheduled), or to change a page's kind to or from legal. Unscheduled drafts can be edited with `content.write`.
  - Production refuses to publish text still marked "[DRAFT", the same test consent texts use, to leave such text on a live legal page, and to move it into or out of the legal kind. Development and tests allow it, so the suite can run the flow.
  - A scheduled publish that is blocked is cancelled and audited rather than retried every tick.
  - `legal_version` is typed by staff.
- **System pages:** home, projects, about and contact can't be created. They and the seeded legal pages (privacy, terms, disclaimer) are required pages (`is_required`): they can't be deleted or archived, and keep their slug and kind; unpublishing is allowed. That keeps the seed's match by slug safe, and the consent texts and footer can link to them. A short list of slugs is reserved for the site's own sections.
- **Scheduling:** a live page can't be given a publish time, and every take-down clears it, so a stale time can't bring a page back.
- **Concurrent edits:** page saves may send `expected_updated_at`; a stale one is refused with 409, so a stale tab can't drop someone else's blocks.
- **Public paths:** `/` for home, `/<slug>` for pages, `/blog/<slug>` for posts, `/projects/<slug>` for projects.
- **Redirects:**
  - Every active redirect is one hop, enforced under one advisory lock. Chains collapse in both directions, and a loop is refused with 409.
  - An `https://` URL on one of our domains is stored as its path. The default code is 308.
  - Slug changes on live projects, pages and posts create or re-point redirects. Publishing deletes any redirect *from* the item's own path; otherwise renaming back and forth would make a loop.
  - A stored target never starts with `//` (no open redirect; CHECK backstop). Collapsing a chain keeps the original target's query string and fragment when the onward target has none.
  - A manual redirect can't start at the address of a live page, post or project.
  - Phase 5 contract: paths match exactly and case-sensitively; only the reserved-path check (`/admin`, `/api`, `/_next`, `/_internal`) ignores case.
- **Offers:**
  - `is_active` defaults to false, so new offers save as drafts.
  - No countdown field exists, and pressure wording ("only N left", "hurry", "last few", "selling fast") is refused.
  - A light pattern asks for a terms line or T&C link when the text mentions a price or discount. It is a prompt, not legal review.
  - An offer that has been live, or that a page shows, can't be deleted; switch it off instead.
- **Testimonials:** real only. There's no sample flag, the seed creates none, and a database CHECK stops one being shown without a source and consent date. Audit diffs record `[hidden]` instead of names, words and the source, events carry ids only, and media usage names a testimonial by the person's initials.
- **Deleting** an FAQ or testimonial removes it from every block that picked it; a block left with no picks is hidden rather than widened to "all FAQs" or "newest testimonials". A project that a page block or an offer names can't be deleted.
- **Errors:** a field literally named `body` (post body, lead note body, consent text body) used to be reported as `request`; it is now `body`. Union tags are left out of error paths.
- **CMS:**
  - One "Save draft" saves both the page fields (PATCH, changed fields only) and the blocks (PUT of the full list). Publish waits until changes are saved.
  - The block preview is a rough CMS preview with [bracketed] stand-ins for live data. The public rendering is Phase 5.
  - Formatted text: bold and italic work within one line; the nearest closing mark wins; a tab counts as two spaces; `- ` needs text after it to become a bullet; nesting stops at four levels.
  - Offer, testimonial and redirect editors open beside their lists, with the selected item in the address. Those lists page 25 at a time.
  - Without `offers.manage`, the offer-banner block can only pick by placement; an offer already chosen shows read-only.
  - A live or scheduled legal page is read-only in the editor without `legal.publish`, and required pages hide Delete, Archive and the address and kind fields.
  - The web app gets its own unit tests (Vitest 5.0.5, the version `@empire/ui` already uses) for rules a browser test can't reach without another sign-in, such as the legal-page rights. CI runs them.
- **Where the CMS differs from the design boards, and why:**
  - Search and Construction progress blocks aren't offered (no API type yet). The board's approval flow for counts is replaced by the required source and as-of fields plus show/hide.
  - Testimonials: the source is free text with suggestions; the permission-document upload and "written permission" tick box are replaced by the consent date, because the API stores no document.
  - Offers: one placement instead of several "Show on" boxes, and "Switched on" instead of a schedule toggle, following the API.
  - The page editor has no link to the live page yet (no public pages), no drag handles (move buttons only) and no "restorable versions" (no versions are kept).
  - FAQs show one group at a time with a filter, so reordering stays within a group.
- **Not built yet:**
  - Public content endpoints, the sitemap and redirect hit counting (Phase 5).
  - The private permission document for testimonials.
  - Deleting a city doesn't yet check grid blocks that filter on it.
  - The block pickers (one offer, chosen FAQs, testimonials, projects) load the first 100 rows only.
  - Child URLs under a renamed project: a project slug change redirects `/projects/<old>` only. Phase 5 decides the URL scheme for configuration pages; if they sit under the project path, it adds a prefix redirect.
  - Hindi translations UI (flag `locale_hi`).
- **Contract changes:**
  - Additions: `PUT /admin/faqs/order`, `GET /admin/media/{id}/usage`; `*Update` PATCH bodies with every field optional; `PageSummary`/`PostSummary` list rows; `path`, `seo_warnings`, `publish_blockers` and `og_image` on pages and posts; `terms`, `terms_url`, `state` and `has_been_live` on offers; `can_show` on testimonials; `origin` and `notices` on redirects; `project_name` on FAQs, offers and testimonials; filters `site_wide`, `category`, `placement`, `state`, `project_id`, `is_visible`, `origin` and `is_active`.
  - Added after review: `is_required` on pages, and an optional `expected_updated_at` on page saves (409 when stale).
  - Tightened: times must carry a time zone, ratings are 1–5, consent dates can't be in the future, and translated fields have the same length limits as their English fields.
**Verified / assumed:**
- No new dependencies in the API or the web app.
- YouTube links are accepted as `watch?v=`, `youtu.be/`, `embed/`, `shorts/`, `live/` and `v/`; Vimeo as `vimeo.com/<id>` and `player.vimeo.com/video/<id>`. Assumed from the providers' current URL formats; not checked against their APIs.
- The SEO warning lengths (60 and 160 characters) are where search results usually cut titles and descriptions. They are guidance, not limits.

## D-036 · Phase 4 part 5: settings, users, two-factor sign-in and email (Accepted, 2026-10-26)

**Context:** Part 5 finishes the CMS core: settings, users and roles, the audit log, the consent-text screen, the forgot/setup/reset pages, two-factor sign-in for admins, and email. There is no Resend key yet, so email runs through a local dev mailbox until staging (Phase 9).
**Decision:**
- **Two-factor (TOTP):**
  - Our own RFC 6238 code (no library), tested with the RFC's vectors. Secrets Fernet-encrypted; ten recovery codes stored as keyed hashes and shown once; each time step accepted once per account.
  - An account with two-factor on is **always** asked for a code, not only while flag `admin_2fa` is on. That is stricter than the spec's wording: someone who turned it on expects it, and it lets the browser suite test it without switching the shared flag. The flag additionally forces admins and super-admins without it to set it up at sign-in.
  - Switching `admin_2fa` on is refused unless the super-admin doing it has two-factor on, so the switch can't lock them out.
  - With two-factor, `login` answers 202 with no session and a 5-minute single-use `__Host-empire_2fa` cookie bound to the account and network (a contract deviation: the contract only had 200).
  - Wrong codes share the D-027 per-account-and-network lockout counter. A correct password with a code still pending doesn't reset it; otherwise password plus four wrong codes, repeated, would never stop. Codes are also capped at 20 per account per hour across networks. The code step doesn't count toward the 10-per-network sign-in limit.
  - Proof while signed in: setting up needs the password; turning off needs the password and a code; new recovery codes need a code. Turning it on signs out the account's other sessions.
  - The recovery-code hash key is derived from `DATA_ENCRYPTION_KEY`, not `SESSION_SECRET`, because the runbook rotates `SESSION_SECRET`. Rotating the data key means everyone sets two-factor up again.
  - Known limit of forced set-up: whoever knows the password before the person enrols can enrol their own phone. The "two-factor was turned on" email is the warning.
  - Break-glass: `empire-api reset-two-factor --email …` on the server, for a lone super-admin who lost both phone and codes. Audited; signs the account out everywhere.
- **Email:**
  - One interface, two transports: Resend over the existing `httpx` (no SDK) and a dev mailbox (`apps/api/.mail-dev/`, git-ignored) for development, tests and the browser suite. Staging and production refuse to start without `EMAIL_API_KEY` and `EMAIL_FROM`, or with the dev mailbox. `GET /api/v1/dev-mail/latest` exists only with the dev mailbox in development or test.
  - Idempotency: Resend's `Idempotency-Key` (event, template and recipient) plus a local `email_message` log of keyed hashes, because Resend keeps keys for 24 hours while outbox retries run for about 32.
  - Errors: 401/403, 429 (including the Free plan's daily quota), 5xx and network errors are retried on the outbox schedule; a 409 "request body changed for this key" counts as sent; other 4xx go dead at once with an alert line (a new permanent-failure branch in the drain). Dead emails show on the dashboard.
  - Who gets what: setup and reset links to the person; security notices (locked at most once an hour, password changed, two-factor on, off or reset); new leads only when `data.alert` is true, to the sales inbox or, when it is empty, every active super-admin; "now yours" to an assigned owner (not on self-assignment); one email per site-visit request. Nothing for sample, spam or erased leads. `user.created` sends no separate email, because the setup-link email covers it.
  - COMPLIANCE: lead emails carry the name and a masked phone with a link to the CMS, never the full phone, email or message.
- **Settings:**
  - Nine typed groups following the Settings board, with checks (GSTIN format and check character, the leads phone rule, social links on each network's own hosts, tracking-ID formats, a `{page}` token in the WhatsApp message, a sender name that can't inject mail headers).
  - Per-group permissions: the PATCH route is marked `settings.read` and each group checks its own permission (`x-permission-by-group`), so marketing can save tracking and SEO defaults (a contract deviation). Lead retention is super-admin only, 1–10 years.
  - The RERA authority and portal are fixed, and "show RERA everywhere" can't be switched off (D-002).
  - `GET /admin/settings` returns a typed overview with the round-robin preview and an integrations status that never shows a key. "Connected" means the key and sender are set, not checked live with Resend.
  - Placeholder keys were renamed (only placeholders were stored): `company.address` became registered and corporate addresses; `contacts.whatsapp`/`hours` became `whatsapp_number`/`office_hours`; `seo_defaults.description` became `default_description`.
- **Lead routing:** one rule decides who can own a lead: an active account that has set its own password and whose role can open leads. Round robin, the single owner, duplicates, `GET /admin/lead-owners`, reassignment and manual leads all use it, so an invited account never gets leads. Round robin can pause a person without removing them.
- **Password-reset requests:** at most 3 per hour and 5 per UTC day per email (counted before the account is looked up), so one targeted address can't use up the Free plan's 100 emails a day.
- **Users and audit:** invites never return the link; the role table comes from `GET /admin/permissions`; the audit log shows IPs masked, filters on IST days (`from`/`to` were UTC in the contract) and by action prefix, and nothing in this part writes to it except the usual audit rows.
- **CMS:**
  - Settings sections keep the open section in the address (`?tab=`), so dashboard tasks land on the right section; rights come from the API's `can_edit`.
  - Setup and reset pages read the token once, remove it from the address bar, send `Referrer-Policy: no-referrer` and load nothing from other sites.
  - The unsaved-changes guard lets downloads and `blob:`, `mailto:` and `tel:` links through (it used to block the recovery-codes download).
  - Audit filters are presets the API can answer (sign-ins, accounts, settings, flags, consent texts, leads, exports, erasures, projects, pages) instead of the board's six chips, two of which aren't prefixes.
  - The browser suite never switches `admin_2fa` on (the database is shared and specs run in parallel). It tests an account with two-factor on, end to end. A run now uses 6 sign-ins.
- **Where the CMS differs from the design boards, and why:** no "+ Add a state", webhook table, share-image upload or sitemap links yet (no API for them); lead routing is a mode choice; no "Keep me signed in" (session lifetimes are fixed); the invite form asks for a name (the API needs it); sample accounts are marked by their "Sample …" name.
- **After review:** open sign-in challenges close whenever sessions are revoked; a wrong current password on password change counts on the lockout; a new link burns older ones (and so do email changes and deactivate/reactivate); links carry the token in the URL fragment; forced set-up and switching `admin_2fa` on sign out password-only sessions; a super-admin can't reset their own two-factor through the admin endpoint; lead routing checks only newly added people, so a deactivated person in the list never blocks saving, and they can be removed; a database trigger refuses UPDATE and DELETE on `audit_log` (TRUNCATE stays possible for tests); the sender name allows letters, digits, spaces and `. - & '` only, and the From header is built with `formataddr`; SEO defaults need `seo.manage` and `settings.read`, so content editors can't save them.
- **Not built yet:** webhooks, CRM and WhatsApp alerts (Phase 6); `/public/site` and a default share image (Phase 5); a list of everyone who appears in the audit log for admins without `users.manage` (`TODO(phase-6)`).
**Verified / assumed:**
- Resend (resend.com/docs, read 25 Oct 2026): `POST https://api.resend.com/emails`; `Idempotency-Key` up to 256 characters, kept 24 hours; 10 requests per second per team; the Free plan's daily quota resets at midnight UTC and answers 429 `daily_quota_exceeded`. Free plan 100 a day and 3,000 a month (D-007). The error body's `name` field is assumed; the docs don't name it.
- segno 1.6.6 (PyPI, released 12 Mar 2025, still the newest on 25 Oct 2026; BSD, pure Python, no dependencies) draws the QR code as an SVG data URL.
- No real email has been sent: there is no key yet.

## D-037 · From Phase 5: a developer agent builds, Claude manages and tests (Accepted, 2026-10-26)

**Context:** The owner wants the remaining phases built by another AI agent (Antigravity, on the owner's computer), with Claude managing and testing the work the way it ran Phase 4. Claude still has no GitHub access (D-029).
**Decision:**
- **Roles:** the developer agent builds one task at a time on its own `feat/…` branch in the owner's working copy and pushes that branch from the owner's computer. Claude writes the task docs and prompts, reviews every pushed branch, runs all checks, has an independent reviewer read the code, and tells the owner whether to merge. The owner opens or approves the PR and merges with Squash and merge.
- **Where things live:**
  - Committed: the process ([agents/WORKFLOW.md](agents/WORKFLOW.md)), the task docs ([tasks/](tasks/README.md)), and the phase plans.
  - Private, in the owner's `docs/` folder: the developer's reports (`docs/agent-reports/`), the manager's reviews (`docs/reviews/`), the paste-in prompts (`docs/agent-prompts/`) and the design boards (`docs/design-boards/`).
- **Task size:** Phase 5 is split into seven tasks instead of five parts, because one agent works serially and smaller pull requests are easier to review. Each task doc is written after the previous task merges.
- **Decisions:** the developer proposes the next `D-0xx` as "(Proposed)"; the manager accepts or changes it at review.
- **Gate:** a merge needs a green CI and the manager's "Merge" verdict. The owner can always overrule.
**Verified / assumed:** Antigravity reads a root `AGENTS.md` (since IDE 1.20.5, per a third-party guide dated 5 Aug 2026; Google's own docs weren't checked), so the agent rules stay in `AGENTS.md`. Each rules file is limited to 12,000 characters; `AGENTS.md` is about 3,600.

## D-038 · Public API read-only endpoints, caching and search (Accepted, 2026-11-01)

**Context:** Task 5.1 builds the 13 read-only public endpoints under `/api/v1/public/*` needed by the public website. They must return only published, non-off-market data in shapes made for the site, without leaking staff fields, drafts, private notes, or sample data in production.

**Decision:**
- **Visibility rules:**
  - Enforced centrally in `visibility.py` across all endpoints, project and property lists, blocks, detail queries, and sitemaps.
  - Published only (`publish_state = 'published'`); `sales_status = 'off_market'` items are hidden; `sold_out` items appear after `available` ones with their badge.
  - Sample isolation (D-015): in production (`APP_ENV = 'production'`), `is_sample = true` rows are excluded everywhere (including blocks, grids, sitemaps, media, and counts). In development, test and staging they are returned with `is_sample: true`.
  - Placeholder sanitization: values containing bracketed `[placeholder]` text return `null` across all settings groups (`company`, `contacts`, `social`, `regulator`, `seo_defaults`) in production, preserving development inspection elsewhere.
  - Gated brochure protection: when `brochure_gated = true`, the public project detail returns `brochure: null` (preserving `brochure_gated: true` indicator) so delivery URLs cannot be accessed without submitting a lead form with consent.
- **Hero/cover image selection rule:**
  1. The pinned cover (`is_cover = true`) if visible and carrying an honest label (`artist_impression`, `actual_photo`, `progress_photo`).
  2. Otherwise, the first visible labelled gallery photo in `sort_order`.
  3. Otherwise, `None` (no image displayed).
  In production (`APP_ENV = 'production'`), sample media (`is_sample = true`) is strictly excluded from cover selection.
- **Search and typo tolerance (ARCHITECTURE §14):**
  - PostgreSQL generated columns cannot reference foreign tables, so `project.search_vector` generated `tsvector` column indexes `name` and `tagline` directly on the project row.
  - Search queries combine `Project.search_vector @@ plainto_tsquery` with `EXISTS` subqueries over `city` and `locality` to prevent duplicate join collisions when `city` or `locality` filter chips are also active.
  - Typo tolerance uses `pg_trgm` word similarity operators (`cleaned_q <% col`), accelerated by GIN `gin_trgm_ops` indexes on `project.name`, `locality.name`, and `city.name`.
  - The `pg_trgm.word_similarity_threshold` is set to `0.5` per transaction via `SELECT set_config('pg_trgm.word_similarity_threshold', '0.5', true)` executed within the search transaction. This transaction-local setting functions reliably across connection poolers (such as Neon's PgBouncer in transaction mode) where startup options and session-level settings do not persist. `0.5` allows matching 1 typo in 5-7 letter Hindi/Indian place and project names (e.g. "Emerld" -> "Emerald", "Noida" -> "Noyda", "Gomti" -> "Gomati"), whereas PostgreSQL's default `0.6` is too strict for short word typos and fails on 5-character names with 1 transposition.
  - Catalogue project search orders by search relevance (`ts_rank` and `similarity`) when `q` is provided and default `sort=recommended` is selected.
  - Migration `0007_search.py` adds `search_vector` and GIN indexes with a clean upgrade → downgrade → upgrade cycle.
  - Admin `list_projects` in `projects/service.py` adopts FTS + trigram matching alongside substring `LIKE` matching for slugs and names, and orders by relevance (exact match first, then prefix, then substring LIKE, then full-text rank, trigram similarity, updated_at and id) when `q` is provided.
- **Caching and limits:**
  - Responses set `Cache-Control: public, max-age=60, stale-while-revalidate=300` and SHA-256 `ETag`.
  - Weak ETag matching (RFC 9110 §13.1.2) strips `W/` prefixes before comparison, returning `304 Not Modified` on matching `If-None-Match`.
  - Error responses (404, 429) set `Cache-Control: no-store`.
  - Public rate limit is set to 120 requests/minute per network bucket (`public:{hash_ip(network_key(ip))}`). Network keys (/64 for IPv6, /32 for IPv4) are hashed via HMAC-SHA256 (`hash_ip`) to comply with SECURITY §8 personal data protection.
  - 120 req/min was chosen to provide a generous budget for legitimate human visitor browsing, SPA prefetching and multi-tab exploration, while stopping scraping bots and request flooding.
  - Internal Next.js server-side renders (SSR / ISR) and build-time static pre-renders (`next build`) pass edge verification without client IP headers; these are routed to a dedicated bucket `public:server` with a limit of 3,000 req/min (window 60s). This prevents the API from failing open (unlimited traffic) if edge headers are omitted or misconfigured, while providing high throughput for web server renders.
- **Testimonial privacy:**
  - Public testimonials (`PublicTestimonial`) expose only public information: `id`, `person_name`, `person_detail`, `quote`, `rating`, `photo`. Internal tracking and audit fields (`consent_date`, `source_url`, `project_id`) are stripped from public responses.
- **Sitemap paths and deterministic timestamps:**
  - Sitemap entries are restricted to canonical content URLs: `/`, published standard/legal pages (`kind != "landing"`, `seo.noindex = false`, and without draft placeholder text `is_draft_text = false`), published projects (`seo.noindex = false`), published posts (`seo.noindex = false`), and `/blog`.
  - Configuration URLs (`/projects/{slug}/configurations/{config_slug}`) and city search filter URLs (`/projects?city={slug}`) are excluded from the sitemap.
  - `lastmod` timestamps are derived deterministically from the underlying database rows (`max(updated_at)` for collection routes `/` and `/blog`, row `updated_at` for items) rather than `utcnow()`, enabling reliable HTTP 304 caching for search engine crawlers.
- **Offer placement blocks:**
  - An `offer_banner` block configured by placement (e.g. `placement = "home"`) returns the single highest priority active live offer matching that placement.
- **Translations (D-014):**
  - English default; Hindi overlay from `translations` JSON column when `locale = 'hi'` and feature flag `locale_hi` is enabled. If disabled or missing in Hindi, values fall back cleanly to English. Public responses drop the raw `translations` dictionary to avoid bypassing Hindi gating.
- **SEO share image resolution:**
  - Public `seo` responses resolve `og_image_id` into a `PublicMedia` object (`PublicSeo.og_image`) with delivery URL, dimensions, and format, enabling immediate rendering in meta tags.
- **Performance:**
  - Project detail and pages batch-load media links, FAQs, testimonials, and offers in single queries.
  - Page grids fetch up to `limit` items directly without running count subqueries, and property detail loads summary data without loading full project detail graphs.

**Consequences:** The public website in 5.2+ can render all public pages and listings with 1–2 lightweight API calls. Neon and PostgreSQL 18 support `pg_trgm` natively. Cache headers and ETags enable browser and CDN caching while protecting backend databases.
**Verified / assumed:**
- `pg_trgm` extension is created in migration `0001_foundation.py:25`, so migration `0007_search.py` requires no superuser privileges on Neon.
- Query performance verified bounded via test query counters.

---

## D-039 · Website shell, server-side data layer, revalidation, CSP and observability (Accepted, 2026-11-02)

**Context:** Task 5.2 establishes the public shell for the Empire website, wired to the 5.1 public read-only API. It requires a dedicated public route group layout, server-side data fetching with Next.js cache tags, an end-to-end signed cache revalidation pipeline, brand-compliant shell components, a Cloudinary media loader, nonce-based CSP, privacy-preserving Sentry error tracking, and Noir-styled 404/error pages.

**Decision:**
- **Public route group:**
  - `app/(site)/` wraps all public pages with `layout.tsx` (Header, Footer, MobileActionBar, OfferBanner, SampleDataRibbon) and `page.tsx` for the home page.
  - The admin CMS routes (`app/admin/`) and edge proxy behavior (`src/proxy.ts` for `/api/*`) remain untouched in their own layout and contract.
- **Server-side data layer (`lib/public/api.ts`):**
  - Typed server-only wrapper over `@empire/api-client` sending edge authentication headers (`X-Empire-Edge-Key` only; server render requests use the API's server rate limit bucket without visitor IP).
  - Next.js tag-based caching with 1-hour safety revalidate fallback: tags include `content`, `site`, `project:<slug>`, `projects`, `properties`, `page:<slug>`, `posts`, `post:<slug>`, `faqs`, `testimonials`, `redirects`.
  - 404 responses from the API invoke Next.js `notFound()`; other API failures trigger the error boundary rather than displaying invented or partial data.
- **Signed revalidation protocol (end-to-end):**
  - **Web receiver (`POST /_internal/revalidate`):** Accepts a JSON body `{ "tags": [...] }` and headers `X-Revalidate-Signature` (hex HMAC-SHA256 over `${timestampMs}.${rawBody}` using `REVALIDATE_SECRET`) and `X-Revalidate-Timestamp` (Unix timestamp in integer milliseconds). Validates 64-character hex format (`/^[0-9a-f]{64}$/i`), constant-time signature match, enforces a 5-minute freshness window against current server time, tracks verified signatures in an in-memory sliding cache to refuse replays, and calls `revalidateTag(tag, { expire: 0 })`. (The in-memory replay cache is per-instance; an external store like Redis can be added in Phase 9 if multi-instance web containers require cluster-wide replay deduplication). Stale, invalid, suffixed or unsigned requests answer 401 with no details.
  - **API sender (`integrations/revalidation.py`):** Outbox handler maps domain events (`project.*`, `configuration.changed`, `construction_update.published`, `media.*`, `page.*`, `post.*`, `faq.changed`, `testimonial.changed`, `offer.*`, `settings.updated`, `flag.changed`, `redirect.changed`, `consent_text.published`) to corresponding cache tags. Signs the payload with `REVALIDATE_SECRET` and sends to `WEB_REVALIDATE_URL`.
  - **Outbox isolation (M2):** Revalidation runs in the outbox drain with error isolation so temporary web unavailability never blocks domain handlers (such as Cloudinary asset destruction for `media.removed`). Failed revalidations emit a dedicated `web.revalidate` event to handle retries independently.
- **Shell components & Design System:**
  - Follows design boards (`NoirComponents`, `NoirHome`, `NoirMobileHome`, `Noir404`).
  - **Header:** Logo from `brand/`, navigation items from `/public/site` (`show_in_nav`, in order, plus Projects), "Book a site visit" CTA linking to `/contact`, skip link (`#main-content`), and accessible mobile drawer with keyboard focus trap, Escape to close, and focus restoration.
  - **Footer:** RERA registration disclaimer, UP-RERA portal link (`up-rera.in`), official channels notice (`empirebuildcon.com`), social links with minimum 44 px tap targets, legal navigation (Privacy, Terms, Disclaimer), and copyright year.
  - **Mobile action bar:** Sticky on phone viewports (`md:hidden`), equal-weight Call and WhatsApp actions, WhatsApp `{page}` replacement with current path, and Enquire CTA.
  - **Offer banner:** Displays first active banner offer from `/public/site` for the placement; dismissible for the browser session via `sessionStorage`. Shows date validity line when `starts_at` and `ends_at` are provided.
  - **Sample data ribbon:** Amber warning banner displayed when viewing sample data (`has_sample: true` on public site) in non-production environments.
  - **Placeholders & missing data:** Values enclosed in `[brackets]` are hidden in production (`APP_ENV = 'production'`).
- **Media delivery:**
  - Cloudinary custom loader in `lib/cloudinary-loader.ts` generates `c_limit,f_auto,q_auto,w_<width>` transformations for Cloudinary URLs while leaving external/local images untouched.
  - `PublicImage` component wraps `next/image` with honest labels (`artist_impression`, `actual_photo`, `progress_photo`) and mandatory alt text.
- **Content Security Policy (CSP):**
  - Set per request in `src/proxy.ts` (matching pages while leaving `/api/*` proxy intact; edge authentication headers are added strictly to `/api/*` requests).
  - Report-only by default (`Content-Security-Policy-Report-Only`), enforced with `CSP_ENFORCE=true`.
  - Directives: `default-src 'self'`, `script-src 'self' 'nonce-<nonce>'` (plus `'unsafe-eval'` in development), `style-src 'self' 'unsafe-inline'`, `img-src 'self' https://res.cloudinary.com data: blob:`, `font-src 'self'`, `connect-src 'self' https://api.cloudinary.com <sentry-host>`, `media-src 'self' https://res.cloudinary.com blob:`, `frame-ancestors 'none'`, `form-action 'self'`, `object-src 'none'`, `base-uri 'self'`, `report-uri /_internal/csp-report`.
  - Dynamic pages receive a per-request nonce-based CSP (`script-src 'self' 'nonce-<nonce>'`). The static auth pages (`/admin/setup`, `/admin/reset`, `/admin/forgot`) receive `'unsafe-inline'` script-src so they can remain pre-rendered without runtime server HTML serialization of `?token=` parameters in the RSC flight payload.
- **Sentry error tracking:**
  - `@sentry/nextjs@11.10.0` initialized via `instrumentation.ts` and `instrumentation-client.ts`, wired with `withSentryConfig` in `next.config.ts`, active when `SENTRY_DSN` or `NEXT_PUBLIC_SENTRY_DSN` is configured.
  - Default SDK data collection disabled via `dataCollection: { userInfo: false, cookies: false, httpHeaders: false, httpBodies: [], urlQueryParams: false, databaseQueryData: false }`.
  - Privacy scrubber (`lib/sentry-scrubber.ts`) strips query strings and fragments from URLs, request bodies, cookies, visitor IP addresses, header allowlist, and scrubs root span attributes in `contexts.trace.data` and child span attributes.
- **404 & error boundaries:**
  - `app/not-found.tsx` matching `Noir404` with quick links to Projects, Properties, Contact, and Home, retaining `robots: noindex`.
  - `app/error.tsx` catching client/server runtime errors, logging to Sentry, and providing on-brand recovery.

**Consequences:** The public website shell is fully functional, styled according to the brand design boards, and tightly integrated with the public API and outbox invalidation system. The public site and audited CMS screens operate under an enforced CSP with zero console violations.
**Verified / assumed:**
- `@sentry/nextjs@11.10.0` verified on npm as of 1 Nov 2026.
- End-to-end cache invalidation verified in Playwright browser tests (`qa/specs/public-shell.spec.ts:184`) with live outbox drain reflection.

## D-040 · From task 5.3: two build tracks in parallel (Accepted, 2026-11-02)

**Context:** With one developer agent working serially, Phase 5 moved slowly: each task took several review rounds, and nothing else could move while it was open. On 2 Nov 2026 the owner asked Claude to build tasks as well, in parallel with the developer agent, keeping the complex tasks for itself and giving the agent work that neither track waits on.
**Decision:**
- **Two tracks.** Track A (Claude) builds the critical path: 5.3 projects and properties, 5.4 lead forms, 5.5a page-builder pages (home, About, Contact, legal, landing pages), then the rest of SEO and the performance pass. Track B (the developer agent) builds work with no dependency on Track A: 5.5b blog, then the standalone pieces listed in [tasks/phase-5/PLAN.md](tasks/phase-5/PLAN.md). Neither track waits for the other to merge.
- **Ownership, to avoid conflicts.** Each task doc lists the folders it may change. Track B doesn't change `apps/api`, the API contract, migrations, `proxy.ts`, `lib/edge.ts` or the shell components unless its task doc says so. Track A owns those.
- **Decision numbers** are reserved in the plan per task, so two open branches never take the same `D-0xx`.
- **Merging:** whichever branch merges second rebases on the new `main` (or merges `main` into the branch) and re-runs the checks before the final review.
- **Claude's own branches** follow the same workflow as the agent's: task doc, branch, every check in WORKFLOW §4, the full pytest suite twice and `pnpm e2e` twice. An independent reviewer that didn't write the code reads the diff, so the work isn't graded by its author. Claude still has no GitHub access (D-029): it hands the branch to the owner's folder as a git bundle, and the owner pushes it and opens the PR. Only the owner merges.
**Verified / assumed:** none; this is a process decision by the owner.

## D-041 · Projects and properties pages: paths, filters, map and two fixes (Accepted, 2026-11-03)

**Context:** Task 5.3 builds the catalogue pages on the 5.1 API. Configuration and city pages had no public path yet (D-038 left them out of the sitemap). The boards show a map, filters, a key-facts strip and a RERA block on every view.
**Decision:**
- **Paths:**
  - a configuration ("property") is `/projects/<project>/<config>`, matching the API route;
  - a city's projects are `/cities/<city>`, and `cities` is now a reserved page slug;
  - the sitemap feed lists both: configurations of listed (not noindex) projects that aren't off-market (no sample rows in production), and cities with at least one listed project, using the latest project change as the date;
  - helpers: `seo/paths.py` (`property_path`, `city_path`) and `lib/public/catalogue.ts`.
- **Filters** live in the URL and work as a plain GET form. Budget is three bands from the boards (up to ₹ 75 L, ₹ 75 L – ₹ 1.5 Cr, above ₹ 1.5 Cr) sent as whole rupees. Anything invalid in the URL is dropped, not shown as an error. `/cities/<slug>` is a 404 unless the city is in `/public/cities`.
- **Honesty on every view:** `ReraBlock` (QR, number, up-rera.in) near the top of project and property pages and again under "Documents & RERA"; the RERA line on every card; prices come only from the API's display text with the tax note; "Price on request" never shows a figure; carpet area first in both units; a sold-out home says so and takes no enquiries. No "only N left" wording.
- **Enquire and site-visit buttons** go to `/contact?project=<slug>` (with `&want=visit` or `&want=brochure`, and `&home=<config>` on property pages) until 5.4 builds the forms. A gated brochure goes the same way.
- **Map:** Leaflet 1.9.4 (latest stable on npm, May 2023; 2.0 is still beta on 2 Nov 2026) with OpenStreetMap tiles, loaded only on "Show map", a circle marker (no image paths), a pop-up built from text nodes, and attribution kept visible. The CSP `img-src` gains `https://tile.openstreetmap.org` (a `proxy.ts` change that needs the owner's approval). The address and a Google Maps directions link are always on the page.
- **Fixes found while building:**
  - **Cache tags:** the public data layer's cache tags never reached the Next.js data cache. The timeout wrapper's `fetch(request, init)` made Next rebuild the Request without the `next` options. Every read now passes its own fetch (`cachedFetch`). Merged separately as `fix/p5-cache-tags`.
  - **Server pages:** `PublicImage` is now a client component, because a server page can't pass the Cloudinary loader function to `next/image`.
  - **Budget filter:** a price with only one end ("From ₹ 78 L") now counts as that figure, instead of being left out of every band.
**Consequences:**
- `/projects` ignores the blocks of the seeded "projects" system page; its SEO fields are used from 5.6.
- Galleries are a grid without a lightbox (5.7).
- The cards have no WhatsApp button yet (the shell's bar has one).
**Verified / assumed:**
- Leaflet and `@types/leaflet` (1.9.22) versions checked on npm on 2 Nov 2026.
- OpenStreetMap tile usage policy read on 2 Nov 2026 (operations.osmfoundation.org/policies/tiles).


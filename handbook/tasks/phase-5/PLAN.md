# Phase 5 · public website: plan

**Goal:** the website buyers see at `https://empirebuildcon.com`, built on the CMS data from Phase 4 and the approved "Black & gold (dark)" boards (owner approval, 22 Oct 2026). Every project view stays honest: RERA number, QR code and up-rera.in, carpet area first, the price note, no false urgency, nothing invented.

**Who builds it:** two tracks in parallel from task 5.3 (D-040). **Track A** is built by Claude, **Track B** by the developer agent (Antigravity); Claude reviews both. Each task is one branch and one pull request ([../../agents/WORKFLOW.md](../../agents/WORKFLOW.md), D-037). Neither track waits for the other: Track B gets work that doesn't depend on any open Track A branch.

## Tasks

| Task | What | Main parts | Depends on |
|---|---|---|---|
| **5.1** Public API | Every `GET /api/v1/public/*` endpoint the site needs, with no staff fields or personal data | `/public/site`, projects, properties, cities, pages (blocks resolved), posts, FAQs, testimonials, redirects, sitemap; full-text project search; caching headers | Phase 4 |
| **5.2** Website shell | The frame every public page sits in | Root layout, header and menu, footer, mobile Call/WhatsApp bar, data-fetch layer with cache tags, revalidation from publish events (`/_internal/revalidate`), Cloudinary `next/image` loader, nonce-based Content-Security-Policy (report-only on staging first), Sentry for the web, 404 and error pages | 5.1 |
| **5.3** Projects and properties | The pages people come for | Projects list with filters in the URL, project detail (RERA block, gallery with honest labels, floor plans, amenities, specifications, location advantages, construction progress, payment plans, FAQs, brochure), property (configuration) page, city pages, Leaflet map | 5.2 |
| **5.4** Lead forms | Turning visitors into leads, with consent | Enquiry, site visit and brochure forms; two separate consent boxes, never pre-ticked; consent text version stored; UTM and click IDs; honeypot; thank-you state; offline and error states | 5.3 |
| **5.5a** Page-builder pages | Everything built in the page builder | Home, every block's public rendering, About, Contact, legal pages (DRAFT marker until the owner approves), campaign landing pages | 5.4 |
| **5.5b** Blog | News and guides | Blog list with category filter and paging, article page, tags | 5.2 |
| **5.6** SEO | Being found, correctly | Metadata and share images, structured data (`Organization`, `RealEstateListing`/`Residence`, `FAQPage`, `BreadcrumbList`), `sitemap.xml`, `robots.txt`, canonical `.com` URLs, breadcrumbs, the redirects middleware with hit counting | 5.5 |
| **5.7** Performance and extras | Fast and finished | Lighthouse ≥ 90 on mobile in all four scores, Core Web Vitals, EMI calculator, share buttons, saved properties (browser only, no account), a full accessibility and 390 px pass | 5.6 |

## Status (updated 4 Nov 2026)

| Task | Track | State | Pull request / notes |
|---|---|---|---|
| 5.1 Public API | — | Merged 1 Nov | D-038 |
| 5.2 Website shell | — | Merged 2 Nov | #16, D-039 |
| 5.3 Projects and properties | A | Merged 3 Nov | #20, D-041 |
| 5.4 Lead forms | A | Merged 3 Nov | D-043 |
| 5.5a Page-builder pages | A | Merged 3 Nov | D-045 |
| 5.5b Blog | B | Merged 4 Nov | three review rounds |
| 5.6 SEO (metadata, structured data, redirects) | A | Merged 3 Nov | #23, D-047 |
| 5.7 Performance and the 390 px pass | A | Merged 4 Nov | D-049 |
| 5.7b EMI calculator, saved homes | B | Merged 5 Nov | #29, three review rounds | [5.7b-tools.md](5.7b-tools.md) |
| **5.6b** `sitemap.xml`, `robots.txt` | B | **In progress** (developer agent) | [5.6b-sitemap-robots.md](5.6b-sitemap-robots.md) |
| 5.8 Phase 5 finish | A | Merged 4 Nov | #27 |
| **5.7c** Less client JavaScript; performance a hard budget | A | **In review** (`perf/p5-7c-client-js`) | [5.7c-client-js.md](5.7c-client-js.md), D-049 |

**5.8 · Phase 5 finish (Claude, one branch).** These are the loose ends kept from the reviews:
- the blog's metadata through `pageMetadata`;
- performance made a hard CI budget again, once the runner's long task is explained from the saved traces;
- the CMS offers screen's save/selection race;
- the contact page when no project can be chosen;
- "hits are approximate" on the redirects screen;
- the 5.5a nits: cleanup that hides the first error, the legal-version gap, and the RERA panel inside the form block.

**Phase 5 is done when** 5.7b, 5.6b, 5.7c and 5.8 are merged and the Phase 5 checks below are green on `main`. Owner inputs (below) are needed for go-live, not to finish Phase 5.

## Tracks and order (from 2 Nov 2026, D-040)

| Track | Builder | Order | Reserved decision numbers |
|---|---|---|---|
| **A** | Claude | 5.2 merged → **5.3** projects and properties → **5.4** lead forms → **5.5a** page-builder pages → **5.6** SEO (metadata, structured data, redirects middleware) → **5.7** performance and the 390 px pass | 5.3 D-041 · 5.4 D-043 · 5.5a D-045 · 5.6 D-047 · 5.7 D-049 |
| **B** | Developer agent | **5.5b** blog → **5.7b** standalone tools (EMI calculator, share buttons, saved properties, built as components with their own tests) → **5.6b** `sitemap.xml` and `robots.txt` | 5.5b D-042 · 5.7b D-044 · 5.6b D-046 |

- **Who may change what.** Track B doesn't change `apps/api`, the API contract or the generated client, migrations, `proxy.ts`, `lib/edge.ts`, `next.config.ts` or the shell components (`components/shell/`), unless its task doc says so. If it needs one of those, it stops and asks in its report.
- **Second to merge rebases.** When two branches are open, the one merged second brings in the new `main` and re-runs every check before its final review.
- **Track B task docs** are written one ahead, so the agent never waits for a Track A merge.

## Standing rules for every Phase 5 task

- Sample data (`is_sample`) never reaches the public site in production; in development and tests it shows with a SAMPLE marker.
- `[placeholders]` the owner hasn't filled are never shown on the live site as if they were facts: in production they are hidden or shown as "coming soon" wording the task names.
- Public pages work without JavaScript for reading; forms degrade to a clear message.
- WCAG 2.1 AA, no sideways scroll at 390 px, colour never the only signal.
- No third-party scripts, trackers or fonts from other hosts until Phase 6's consent banner; fonts are self-hosted.

## Phase 9 checks collected during Phase 5

- Confirm which header carries the visitor's IP on the web host (`CLIENT_IP_SOURCE_HEADER`, `TODO(phase-9)` in `apps/web/src/proxy.ts`); if it is wrong, every public request lands in the API's shared `public:server` bucket (D-038), which the API logs.
- Switch the Content-Security-Policy from report-only to enforced after a week without violations on staging (5.2).

## Owner inputs (needed before go-live, not to start)

Until these arrive the site uses `[placeholders]` and SAMPLE data that never goes live:
- project list with RERA numbers and QR codes (tracker o-02);
- company details: legal name, GSTIN, addresses, phones, WhatsApp, emails (o-03);
- photos, renders, floor plans and brochures (o-14);
- real testimonials with permission, if any (o-15);
- leadership bios and photos for About (o-16).

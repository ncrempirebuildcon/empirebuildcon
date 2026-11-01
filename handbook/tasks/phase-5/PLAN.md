# Phase 5 · public website: plan

**Goal:** the website buyers see at `https://empirebuildcon.com`, built on the CMS data from Phase 4 and the approved "Black & gold (dark)" boards (owner approval, 22 Oct 2026). Every project view stays honest: RERA number, QR code and up-rera.in, carpet area first, the price note, no false urgency, nothing invented.

**Who builds it:** a developer agent, one task at a time; Claude manages and tests ([../../agents/WORKFLOW.md](../../agents/WORKFLOW.md), D-037). Each task is one branch and one pull request. The next task doc is written after the previous task is merged, so it can build on what actually landed.

## Tasks

| Task | What | Main parts | Depends on |
|---|---|---|---|
| **5.1** Public API | Every `GET /api/v1/public/*` endpoint the site needs, with no staff fields or personal data | `/public/site`, projects, properties, cities, pages (blocks resolved), posts, FAQs, testimonials, redirects, sitemap; full-text project search; caching headers | Phase 4 |
| **5.2** Website shell | The frame every public page sits in | Root layout, header and menu, footer, mobile Call/WhatsApp bar, data-fetch layer with cache tags, revalidation from publish events (`/_internal/revalidate`), Cloudinary `next/image` loader, nonce-based Content-Security-Policy (report-only on staging first), Sentry for the web, 404 and error pages | 5.1 |
| **5.3** Projects and properties | The pages people come for | Projects list with filters in the URL, project detail (RERA block, gallery with honest labels, floor plans, amenities, specifications, location advantages, construction progress, payment plans, FAQs, brochure), property (configuration) page, city pages, Leaflet map | 5.2 |
| **5.4** Lead forms | Turning visitors into leads, with consent | Enquiry, site visit and brochure forms; two separate consent boxes, never pre-ticked; consent text version stored; UTM and click IDs; honeypot; thank-you state; offline and error states | 5.3 |
| **5.5** Content pages | Everything built in the page builder | Home, every block's public rendering, blog list and article, About, Contact, legal pages (DRAFT marker until the owner approves), campaign landing pages | 5.4 |
| **5.6** SEO | Being found, correctly | Metadata and share images, structured data (`Organization`, `RealEstateListing`/`Residence`, `FAQPage`, `BreadcrumbList`), `sitemap.xml`, `robots.txt`, canonical `.com` URLs, breadcrumbs, the redirects middleware with hit counting | 5.5 |
| **5.7** Performance and extras | Fast and finished | Lighthouse ≥ 90 on mobile in all four scores, Core Web Vitals, EMI calculator, share buttons, saved properties (browser only, no account), a full accessibility and 390 px pass | 5.6 |

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

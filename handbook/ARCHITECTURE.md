# Empire website and CMS: architecture

**Phase 1 deliverable** · 18 Oct 2026 · Status: for review
Related: [DECISIONS.md](DECISIONS.md) (why), [SECURITY.md](SECURITY.md), [api/openapi-v1.yaml](api/openapi-v1.yaml), [api/ENDPOINTS.md](api/ENDPOINTS.md), the owner's project brief (private, not in the repo)

Diagram sources are in `diagrams/src/*.mmd` (Mermaid); the `.svg` files next to them are rendered copies that open in any browser.

---

## 1. What we are building

- A public website at `https://empirebuildcon.com` for Empire, a **developer selling its own projects**, starting in **Uttar Pradesh** and able to add any state or city.
- A CMS at `/admin` that non-technical staff use to run projects, media, leads, pages, offers, SEO, users and settings.
- Extension points (events, webhooks, feature flags, a reserved chat slot) so marketing tools, a CRM, WhatsApp and an AI assistant can be added without rework.

## 2. Shape: a modular monolith, API-first

```
empire/                      (repo root = A:\Adarsh\Empire_RealEstate)
├─ apps/
│  ├─ web/        Next.js (App Router, TypeScript, Tailwind) — public site + CMS UI
│  └─ api/        FastAPI — /api/v1, SQLAlchemy 2, Alembic migrations; the background worker is the
│                 `empire-worker` entry point of the same package (D-010, D-026)
├─ packages/
│  ├─ ui/         Design system components built from brand/tokens (Phase 3; spec in handbook/DESIGN_SYSTEM.md)
│  └─ api-client/ Typed TypeScript client generated from the API's OpenAPI spec
├─ qa/            pytest + httpx (API), Playwright + axe (browser), Lighthouse CI
├─ handbook/      Developer guide: architecture, decisions, API, design system, git and code rules (D-025)
├─ brand/         Logo kit and design tokens (brand/tokens/empire-noir.json is the source for packages/ui)
├─ holding-page/  Static "coming soon" page for the domain check
├─ docs/          Owner's private notes — git-ignored, never in the repo (D-003, D-025)
└─ .github/workflows/  CI: lint, type-check, migrate, test, build
```

One PostgreSQL database. Each API module owns its tables, schemas, routes and events; modules talk to each other through service functions, never by reaching into another module's tables, and react to each other through events.

![System overview](diagrams/system.svg)

## 3. Request flow

1. Visitor opens `empirebuildcon.com` (DNS at Cloudflare). `www`, `empirebuildcon.in`, `empirebuildcon.co.in` and their `www` forms answer **308 → same path on `https://empirebuildcon.com`**, query string kept (D-008).
2. The web app serves pages. Public pages are pre-rendered and cached (§5).
3. The browser only ever calls **`/api/*` on the same site**. Next.js rewrites those calls to the API host. The browser never talks to the API host directly, so there is no CORS in production and the session cookie is first-party. The web app's proxy (`apps/web/src/proxy.ts`) adds a shared edge key and the visitor's IP; the API refuses calls without the key, so its host can't be used directly (D-027).
4. **No redirects on the API, ever.** FastAPI runs with `redirect_slashes=False` and a small ASGI middleware that strips a trailing slash before routing, so `/api/v1/admin/projects` and `/api/v1/admin/projects/` hit the same handler. Next.js sets `skipTrailingSlashRedirect: true` so the web host does not add its own 307/308 to `/api/*`. (This is the Current Investor production bug, fixed by design.) A CI test calls every route both ways and fails on any 3xx.
5. Server-side fetches from the web app to the API use a **3-second timeout**. On timeout the page renders its cached/static data and the client refetches (the API host can be slow to wake on free hosting).

## 4. Modules

| Module | Owns | Main endpoints | Emits |
|---|---|---|---|
| `projects` | Project, Tower, UnitConfiguration, Amenity, ProjectAmenity, Specification, LocationAdvantage, ConstructionUpdate, PaymentPlan(+Stage), City, Locality, Location | `/public/projects`, `/public/properties`, `/admin/projects/**`, `/admin/maps/resolve` | `project.*`, `configuration.changed`, `construction_update.published` |
| `listings` | Listing (resale/rent) | reserved; **flag `listings` off** — not built in v1 (D-004) | `listing.*` |
| `media` | Media, MediaLink | `/admin/media/**`, `/admin/media-links/**` | `media.*` |
| `leads` | Lead, LeadConsent, LeadNote, LeadActivity, SiteVisit, Notification | `/public/leads`, `/public/site-visits`, `/public/brochure-requests`, `/admin/leads/**`, `/admin/site-visits/**`, `/admin/reports/utm` | `lead.*`, `site_visit.*` |
| `content` | Page, Block, Post, Faq, Offer, Testimonial, ConsentText | `/public/pages`, `/public/posts`, `/public/faqs`, `/public/testimonials`, `/admin/pages/**` … | `page.*`, `post.*`, `faq.changed`, `offer.*`, `testimonial.changed`, `consent_text.published` |
| `seo` | Redirect; `seo` JSON on content rows; sitemap feed | `/public/redirects`, `/public/sitemap`, `/admin/redirects` | `redirect.changed` |
| `users` | User, Session, PasswordResetToken (roles are a code matrix, §11) | `/auth/**`, `/admin/users/**`, `/admin/roles`, `/admin/audit-log` | `user.*` |
| `settings` | Setting, FeatureFlag | `/public/site`, `/admin/settings/**`, `/admin/flags/**` | `settings.updated`, `flag.changed` |
| `integrations` | WebhookEndpoint, WebhookDelivery, integration config; outbox handlers and the drain | `/admin/integrations/**`, `/admin/webhooks/**`, `/internal/outbox/drain` | — (delivers events) |
| `ai` | KnowledgeChunk (pgvector), ChatConversation, ChatMessage | `/ai/chat` (**flag `chat_widget` off**) | — |
| `platform` (shared) | RateLimitBucket, AuditLog, OutboxEvent (tables and writers), crypto helpers, i18n helpers | `/api/health` | — |

Full list: [api/ENDPOINTS.md](api/ENDPOINTS.md) (159 operations).

## 5. Rendering and caching

| Page type | How it renders | Refreshes when |
|---|---|---|
| Home, project list, project detail, property list/detail, city pages, blog, pages, legal | Static generation + incremental revalidation, tagged (`project:<slug>`, `projects`, `properties`, `page:<slug>`, `posts`, `site`) | The worker calls the web app's signed `/_internal/revalidate` with tags after a publish event; plus a 1-hour safety revalidate |
| Search/filter results | Server-rendered from URL query (`?city=noida&bhk=3`) so links can be shared; cached briefly at the edge | Every request (short cache) |
| CMS (`/admin/**`) | Client-rendered after a server session check; never cached | Always live |
| Lead forms, chat | Client components posting to `/api/v1/public/*` | — |

The `/_internal/revalidate` route lives outside `/api/*` so it is handled by Next.js, not proxied. It requires an HMAC header (`REVALIDATE_SECRET`).

## 6. Data model

![Catalogue](diagrams/erd-catalogue.svg)

![Leads and users](diagrams/erd-leads-users.svg)

![Content and platform](diagrams/erd-content-platform.svg)

**Conventions**

- **IDs:** UUID v7 (time-ordered) for most tables; `bigint` identity for high-volume append tables (audit log, outbox, webhook deliveries).
- **Timestamps:** `timestamptz`, stored in UTC, shown in IST.
- **Money:** whole rupees in `bigint` (`price_min_inr`, `price_max_inr`, `rate_inr`). Display formats as ₹ 85 L, ₹ 1.25 Cr. `price_on_request` hides numbers everywhere, including structured data.
- **Area:** stored once in **square metres** (`size_min_sqm`, `size_max_sqm`) with `display_unit` (sq ft, sq yd, sq m) and `area_basis` (carpet, built-up, super built-up, plot). RERA pages show carpet area where available.
- **Ranges:** every price and size is a min/max pair; equal values display as a single figure.
- **Formatted text:** descriptions, FAQ answers, payment plan notes use WhatsApp-style text (`*bold*`, `_italic_`, `-` bullets, two-space nesting). Stored as plain text; rendered by our own parser into React elements. Raw HTML is never rendered.
- **Translations (D-014):** English lives in the normal columns. A `translations` JSON column holds overlays per locale, e.g. `{"hi": {"name": "…", "tagline": "…"}}`. Missing translations fall back to English.
- **SEO:** a `seo` JSON column on projects, configurations, pages, posts and cities: title, description, OG image, noindex, canonical path.
- **Media links (exclusive arc):** `media_link` has one nullable foreign key per owner type (project, configuration, construction update, page, post) and a check constraint that exactly one is set. Real foreign keys, cascades on delete, one table to query. A partial unique index allows one cover per owner and role.
- **Publishing:** content rows have `publish_state` (draft, published, archived). Projects and configurations also have `sales_status`: **available**, **sold_out** (shown after available items with a "Sold out" badge), **off_market** (hidden from the public site).
- **Sample data (D-015):** rows created by the sample seed carry `is_sample = true`. Public endpoints never return them in production, publish is blocked for them in production, and the CMS shows a "Sample" badge.
- **Deletion:** projects with leads, pages and posts are archived, not deleted. Leads are never hard-deleted by staff; `leads.erase` (super-admin) replaces personal fields with a stub on a data-erasure request and logs it.
- **Units:** the `unit` table (individual flats) is not built in v1 (D-005). Availability is tracked per configuration.

**Indexes worth naming now:** unique `slug` per table; `lead(created_at desc)`, `lead(status, created_at desc)`, `lead(owner_user_id, created_at desc)`, `lead(phone_e164)`; `project(publish_state, sales_status)`; GIN on `project.search_vector` (generated `tsvector`) and `pg_trgm` on project and locality names; `outbox_event(status, available_at)`.

## 7. Listing visibility and order (public site)

1. Only `publish_state = published`, `is_sample = false` (production), and `sales_status != off_market`.
2. Sort: `available` before `sold_out`; within each group, featured order, then the chosen sort (recommended = possession date, then newest).
3. A project page always shows the **RERA authority, registration number, QR code and the regulator's website**. Publish is blocked until the number and QR are present (D-002). Phase-wise registrations show per tower/phase.

## 8. Lead handling

![Lead flow](diagrams/seq-lead.svg)

- **Intake:** one endpoint per intent: enquiry, site-visit request, brochure request. All accept UTM fields and click IDs (`gclid`, `gbraid`, `wbraid`, `fbclid`, `msclkid`) that the site keeps in first-party storage from the landing URL for 30 days.
- **Phone:** normalised to E.164 (`+91XXXXXXXXXX`). Accepted forms include `98765 43210`, `+91-98765-43210`, `09876543210` and `919876543210`.
  - Mobiles are 10 digits starting 6–9.
  - Landlines must include the STD code: 10 digits starting 1–5 after the trunk 0.
  - Foreign numbers aren't accepted yet (`TODO(phase-6)` for NRI leads).
  - "Fancy" numbers (repeated digits, runs) are valid, because operators sell them.
  - The rule follows the DoT National Numbering Plan (D-034).
- **Consent:** the form shows the current consent text. The lead stores the text id, version, time, page URL and the exact checkbox label shown. A lead without consent is rejected.
  - A stale version gets 409 (reload the page).
  - Until an approved text is published, intake answers 503.
  - Marketing consent is a separate, optional record. It is never assumed.
  - Manual leads carry the staff member's note on how consent was given.
  - Consent texts live in the content module. They are versioned and never edited after publishing, and a draft-marked text can't be published in production (D-017).
- **Spam:**
  - A filled honeypot gets the same 201 answer with a look-alike reference, and nothing is stored.
  - Rate limits: 5 per 10 minutes per network (IPv6 by /64) and per phone hash, in PostgreSQL.
  - Duplicates: the same phone and project within 24 hours is saved, linked to the earlier lead (`duplicate_of_id`) and given to the same owner. Its `lead.created` event has `alert: false`, so no second alert goes out.
  - Captcha comes only if spam gets through (flag `captcha`).
- **General leads:** `project_id` may be empty (contact page, NRI page).
- **Assignment (D-016):** in the same transaction as the insert, using `settings.lead_routing`: `single` (everything to one person or the sales inbox), `round_robin` (in turn among listed sales users), or `manual`. Default: single → sales inbox.
- **Pipeline:** new → contacted → site_visit → negotiation → booked / lost (lost needs a reason). Every change writes a `lead_activity` row.
- **Inbox:** newest first, paged, read/unread, with filters in the URL. Dashboard counts link to the filtered inbox (e.g. "12 new" → `/admin/leads?status=new`).
  - INVARIANT: every count shows the same number as the list it opens. The count and the list share one query, with filters such as `open` (still being worked: not booked, lost or erased), `utm_source`/`utm_medium` for the UTM report, `open` on site visits (requested or confirmed) and `blocked` on projects (drafts that can't be published yet). A browser test clicks each count and compares.
- **Object-level access:** without `leads.read_all`, staff see only leads they own. Duplicate links are scoped the same way, and a manual lead links only to an earlier lead its creator can see. This covers the list, detail, notes, activity, visits, export and dashboard. Anyone else's lead answers 404. The UTM report shows counts only; for sales it covers their own leads.
- **Export:** CSV (`leads.export`), streamed and guarded against spreadsheet formulas, with a UTF-8 BOM so Excel shows Hindi names.
  - It is capped at 50,000 rows. Bigger requests are refused, never silently cut.
  - Each export is audited, and each exported lead's timeline records it.
- **Erasure:** `leads.erase` replaces personal fields, notes, the IP hash, consent page URL and stored event payloads with a stub. The reference, status, dates and consent metadata are kept. Leads are never hard-deleted.
- **Retention:** the daily clean-up anonymises leads with no real activity for `privacy.lead_retention_years` (default 3). Reads and exports don't count as activity.
- **Projects with leads** can't be deleted, only archived.
- **Alerts:** email at launch; WhatsApp in Phase 6 (needs WhatsApp Business API).

## 9. Events and the outbox

Every important change writes an `outbox_event` row **in the same transaction** as the change. The worker claims pending rows (`FOR UPDATE SKIP LOCKED`), delivers them, and marks them done or schedules a retry (1 min, 5 min, 30 min, 2 h, 6 h, 24 h, then `dead` with an alert). New features subscribe to events; core code does not change.

Envelope: `{id, type, occurred_at, actor_id, aggregate: {type, id, slug}, data}`. Personal data is included only in `lead.*` and `site_visit.*` events, and only sent to webhook endpoints marked "may receive personal data".

| Event | Emitted when | Consumers |
|---|---|---|
| `project.published` / `project.updated` / `project.unpublished` | Publish, edit while published, unpublish | Revalidate project, lists, properties, cities, sitemap · webhooks · AI index (Phase 7) |
| `configuration.changed` | Any configuration edit on a published project | Revalidate project + properties |
| `construction_update.published` | Update goes live | Revalidate project · webhooks |
| `media.added` / `media.updated` / `media.removed` | Upload, reorder, cover, show/hide, delete | Revalidate the owner if published |
| `media.upload_discarded` | A direct upload was refused or never confirmed | Destroy the file at the store (retried) |
| `lead.created` | Lead saved (`data.alert` is false for duplicates and manual leads) | Email alert · WhatsApp alert (flag) · CRM webhooks · Meta Conversions API + Google Ads conversion (only with marketing consent and flag on) |
| `lead.status_changed` / `lead.assigned` | Pipeline move / owner change | CRM webhooks · email to new owner |
| `site_visit.requested` / `site_visit.updated` | Visit form / CMS change | Sales alert · webhooks |
| `page.published` / `page.unpublished` | Incl. scheduled publish | Revalidate page, nav, sitemap · AI index |
| `post.published` / `post.unpublished` | | Revalidate blog, sitemap · AI index |
| `faq.changed`, `testimonial.changed` | | Revalidate · AI index (FAQs) |
| `offer.started` / `offer.ended` / `offer.changed` | Scheduler tick or edit | Revalidate banners |
| `settings.updated`, `flag.changed`, `redirect.changed`, `consent_text.published` | | Revalidate `site` tag |
| `user.created`, `user.locked` | | Security emails to that user |

## 10. Background jobs

| Job | Frequency | Notes |
|---|---|---|
| Outbox drain | Inside the request right after commit for time-critical events (3 s budget), plus a sweep every 15 minutes | Lead alerts go out within seconds; the sweep retries failures. Every 15 minutes (not every minute) so the free database can sleep (D-007) |
| Schedule tick | Every 15 minutes, with the sweep | Scheduled page publish/unpublish, offer start/end |
| Clean-up | Daily | Expired sessions, reset tokens, old rate-limit buckets, stale upload intents, and anonymising leads past the retention period |
| Backup export | Daily | Only if the database plan has no automatic backups (D-007) |
| Knowledge index | On publish events | Phase 7 |

The worker is one Python function set with two entry points: a long-running loop (paid, always-on hosting) and an HTTP-triggered `/api/v1/internal/outbox/drain` (free hosting, called by a scheduler with `X-Internal-Key`). Same code either way (D-010).

## 11. Roles and permissions

Five roles. One super-admin at launch: `admin@empirebuildcon.com` (the owner). Permissions are checked in the API on every call; the CMS hides what a role cannot do.

| Permission | Allows | Super-admin | Admin | Sales | Marketing | Content editor |
|---|---|:-:|:-:|:-:|:-:|:-:|
| `dashboard.view` | Dashboard | ✓ | ✓ | ✓ | ✓ | ✓ |
| `projects.read` | See projects in the CMS | ✓ | ✓ | ✓ | ✓ | ✓ |
| `projects.write` | Edit projects, towers, configurations, cities, amenities | ✓ | ✓ | | | ✓ |
| `projects.publish` | Publish / unpublish projects | ✓ | ✓ | | | |
| `projects.delete` | Delete draft projects | ✓ | ✓ | | | |
| `media.upload` | Upload, attach, order, cover, show/hide | ✓ | ✓ | | ✓ | ✓ |
| `media.manage` | Delete from the library | ✓ | ✓ | | | ✓ |
| `leads.read` | Open leads assigned to them | ✓ | ✓ | ✓ | | |
| `leads.read_all` | See every lead | ✓ | ✓ | | | |
| `leads.update` | Status, notes, details, manual leads | ✓ | ✓ | ✓ | | |
| `leads.assign` | Change a lead's owner | ✓ | ✓ | | | |
| `leads.export` | CSV export (audited) | ✓ | ✓ | | | |
| `leads.report` | UTM report (counts only, no personal data) | ✓ | ✓ | ✓ | ✓ | |
| `leads.erase` | Erase personal data on request | ✓ | | | | |
| `site_visits.manage` | Visit calendar | ✓ | ✓ | ✓ | | |
| `content.read` / `content.write` | Pages, blocks, posts, FAQs, testimonials | ✓ | ✓ | | ✓ | ✓ |
| `content.publish` | Publish pages, posts, FAQs, testimonials | ✓ | ✓ | | ✓ | ✓ |
| `legal.publish` | Legal pages and consent texts | ✓ | ✓ | | | |
| `offers.manage` | Offers and banners | ✓ | ✓ | | ✓ | |
| `seo.manage` | SEO fields, redirects | ✓ | ✓ | | ✓ | ✓ |
| `settings.read` | See settings | ✓ | ✓ | | ✓ | |
| `settings.write` | Company, contacts, lead routing | ✓ | ✓ | | | |
| `marketing.tracking` | GTM, GA4, Pixel, Ads IDs | ✓ | ✓ | | ✓ | |
| `flags.manage` | Feature flags | ✓ | ✓ | | | |
| `integrations.manage` | Webhooks, CRM, alerts | ✓ | ✓ | | | |
| `audit.read` | Audit log | ✓ | ✓ | | | |
| `users.manage` | Accounts and roles | ✓ | | | | |

Every create, update, delete, publish, export, login and permission change writes an `audit_log` row (who, what, before/after diff, IP).

## 12. Media

![Media upload](diagrams/seq-media.svg)

- **One storage interface, two stores (D-033).**
  - `CloudinaryStore`, using the official SDK, is used in staging and production. Those environments refuse to start without `CLOUDINARY_URL`.
  - `FakeStore` is for development, tests and the browser suite. It keeps files on disk and mimics Cloudinary's signed direct upload, so the whole flow runs offline. Its `/api/v1/dev-media/**` routes exist only when it is active.
- **Photos go through the API.**
  - The browser resizes and re-encodes them first: long edge 2560 px, WebP or else JPEG at about 0.85 quality. The RERA QR is kept as lossless PNG.
  - The web proxy is allowed bodies of 10 MB + 64 KB (`experimental.proxyClientMaxBodySize` in `apps/web/next.config.ts`). Next.js would otherwise cut larger bodies off silently, instead of the API answering 413.
  - The API checks magic bytes (JPEG, PNG, WebP or AVIF only; no SVG), size (≤ 10 MB) and pixels (≤ 25 MP).
  - It strips EXIF/GPS and other metadata, uploads to the store under a generated public id `empire/<env>/<kind>/<uuid>`, and saves the row. The uploaded filename is never used.
- **Videos and documents** (PDF, DOC/DOCX, PPT/PPTX) go **directly from the browser to Cloudinary**:
  1. The API creates an `upload_intent` and signs the upload for that one public id. The intent is valid for 60 minutes, belongs to the user and can be used once. `overwrite=false` is signed too.
  2. The browser uploads and sends Cloudinary's reply to `confirm`.
  3. The API checks the reply signature, matches the intent, re-reads the asset from the Admin API (type, bytes) and only then saves it.
  - Anything refused or never confirmed is destroyed through the outbox.
  - Free-plan limits (checked 23 Oct 2026): 10 MB images and raw files, 100 MB video, 25 MP. Only 40 MB of video can be transformed on the fly, so the video poster is made eagerly at upload.
- **What files can be attached to.** A `media_link` attaches library items to one owner: a project, configuration or construction update (pages and posts come in part 4).
  - **Project roles:** `gallery`, `video`, `document`, `brochure` (PDF) and `rera_qr`. `hero` and `og_image` are reserved: the share image is `seo.og_image_id`, and the hero waits for Phase 5.
  - **Configuration role:** `floor_plan` (image or PDF).
  - **Construction update role:** `gallery` (progress photos).
  - Single-valued roles (brochure, RERA QR, floor plan) replace the previous item.
- **Order, cover and visibility.**
  - Staff set the order. The first *visible* photo is the cover unless another is pinned.
  - Each item can be shown or hidden on the website and renamed.
  - Photos carry an honest label: artist's impression, actual photo, or progress photo with its month. Gallery and hero photos can't be shown on the website without one.
  - A library item can't be deleted while it is attached or used as a share image.
- **RERA QR.** The project's visible `rera_qr` image is what clears the publish blocker. It can't be hidden or removed while the project is live; replace it instead.
- **One drop zone** in the CMS sends each file to the right uploader by type.
- **Delivery** uses Cloudinary transformations (`f_auto,q_auto`, width steps). Every delivered image URL carries a transformation, which also strips metadata.
  - PDFs are stored as images, so they open in the browser and get a page-1 thumbnail.
  - Office files are stored as raw files and download.
  - Public pages use `next/image` with a custom loader (Phase 5).
- **Owner action:** new Cloudinary accounts block PDF delivery until **Settings → Security → "Allow delivery of PDF and ZIP files"** is on.

## 13. Maps

- Staff paste a Google Maps link, a `maps.app.goo.gl` short link or a plus code, and the API extracts the pin (`POST /api/v1/admin/maps/resolve`):
  - **Long links:** the coordinates are read from the URL, in this order: the place pin `!3d…!4d…`; the `q=`, `query=`, `destination=` and `ll=` values; `/maps/search/<lat>,<lng>` and `/maps/place/<lat>,<lng>` (the usual target of a shared dropped pin); and finally the map centre `@lat,lng`.
  - **Short links:** followed on the server only, under the rules in SECURITY.md §5.
  - **Full plus codes** (e.g. `7JWV8XX8+XX`): decoded by our own port of Open Location Code, tested against Google's official vectors (D-031).
  - **Short plus codes** (`8XX8+XX Noida`): refused, with a message asking for the full code or a Maps link.
- Staff can also type the pin. Dragging the pin on a map arrives with the map component in Phase 5.
- The site shows the pin with **Leaflet + OpenStreetMap** tiles, lazy-loaded below the fold, with a pop-up giving the project name, address, RERA number and a "Directions" link to Google Maps.

## 14. Search

- PostgreSQL full-text search (generated `tsvector` over name, locality, city, tagline) plus `pg_trgm` for typos, and structured filters (status, city, locality, type, BHK, budget). Filters live in the URL.
- The `vector` extension (pgvector) is enabled by the first migration wherever the server has it (Neon, CI and the Docker image do), so Phase 7 needs no database change (D-013). A bare local PostgreSQL without pgvector still works until Phase 7 (D-026).

## 15. Languages

English at launch. `next-intl` routing is set up with `en` as the default (no prefix) and `hi` ready under `/hi/...`, switched on by flag `locale_hi` once Hindi content exists. Slugs stay English for both locales; `hreflang` alternates go in the sitemap (D-014).

## 16. SEO

- Metadata and Open Graph images per page (generated OG image using the logo mark and project cover when none is set).
- Structured data: `Organization` (site-wide), `RealEstateListing` / `Residence` for projects and configurations (no price when on request), `FAQPage`, `BreadcrumbList`.
- `sitemap.xml` (split by type), `robots.txt`; canonical URLs always on `https://empirebuildcon.com`; clean slugs; breadcrumbs on every inner page.
- A redirects manager in the CMS (301/308) feeds the web app's middleware.

## 17. Marketing and consent hooks (Phase 6, structure now)

- A consent banner with three choices (necessary, analytics, marketing). GTM/GA4 and Meta Pixel load only after the matching consent; IDs come from Settings, so they can be switched on without a deploy.
- Server-side conversions (Meta Conversions API, Google Ads enhanced conversions) are outbox consumers on `lead.created`, sent only when the lead's marketing consent is true. Phone/email are SHA-256 hashed before sending.
- Campaign landing pages are CMS pages of kind `landing` built from blocks, with their own lead form and `noindex` option.
- WhatsApp click-to-chat on every page (mobile sticky bar) with a prefilled message naming the page.

## 18. AI-ready layer (Phase 7, structure now)

- A chat-widget slot in the layout, lazy-loaded only when flag `chat_widget` is on (off by default).
- `/api/v1/ai/chat` answers 404 while the flag is off.
- Knowledge index (`knowledge_chunk` with embeddings) built from published projects, FAQs, pages and brochures on publish events.
- Tools the assistant may call: search projects, get RERA details, request a site visit, capture a lead with consent, hand over to WhatsApp or a person. Guardrails: no price promises, no legal or financial advice, every answer cites a page. Model provider behind an interface so it can be swapped.

## 19. Environments and hosting

| Environment | Purpose | Where |
|---|---|---|
| Local / Claude's workspace | Development and tests | Any machine with PostgreSQL, or `docker compose up -d db` (PostgreSQL 18 + pgvector); see [SETUP.md](SETUP.md) (D-019, D-026) |
| Staging | Owner review at milestones and gates | Netlify (web) + Cloud Run (API) + Neon branch `staging` |
| Production | Live site | Same providers, separate Neon branch/project and Cloud Run service; free first, step-ups listed in D-007 |

| Piece | Provider (D-007) |
|---|---|
| Web app | Netlify |
| API + worker | Google Cloud Run + Cloud Scheduler |
| Database | Neon (PostgreSQL 18) |
| Media | Cloudinary |
| Outgoing email | Resend |
| DNS, redirects, inbound email, holding page | Cloudflare |
| Errors / uptime | Sentry / UptimeRobot |
| Backups | GitHub Actions (encrypted daily `pg_dump`) |

## 20. Observability

- Sentry for the web app and API (errors + basic performance), release-tagged from CI.
- Uptime checks every 5 minutes on `/` and `/api/health/live` (answers without touching the database, so the free database can sleep), alerting the owner by email. `/api/health` (with a database check) runs after each deploy.
- Structured JSON logs (request id, user id, route, status, duration). No passwords, tokens or full phone numbers in logs (phones masked `+91 98xxxxxx10`).

## 21. Testing (QA suite, built from Phase 3)

| Layer | Tool | Runs |
|---|---|---|
| API | pytest + httpx against a real PostgreSQL | Every push (CI service container) |
| Contract | Schemathesis against the OpenAPI spec; "no 3xx on any API path" test | Every push |
| Browser journeys | Playwright: lead form, CMS login, project edit → publish → visible on site, media upload | Every push (smoke), full nightly |
| Accessibility | axe via Playwright on every template | Every push |
| Performance | Lighthouse CI (mobile) ≥ 90 for performance, accessibility, best practices, SEO | On main |
| Visual | Playwright screenshots, mobile + desktop | Before each gate |

The browser suite signs in as few times as possible: a Playwright setup project signs in the super-admin and a sales user once each and saves their sessions to `qa/.auth/` (git-ignored); the journeys reuse them. With the sign-in tests, a run uses 4 sign-ins, because the API allows 10 per network in 15 minutes, successful ones included (D-027). Locally that is about two full runs per 15 minutes. Public lead intake is limited too (5 per 10 minutes per network), so a run makes one public submission and adds other test leads through the staff API (`qa/README.md`).

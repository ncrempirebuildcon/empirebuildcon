# API endpoints (v1 design)

Generated from [openapi-v1.yaml](openapi-v1.yaml). Permission keys are explained in [ARCHITECTURE.md §11](../ARCHITECTURE.md#11-roles-and-permissions).

## System

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/health` | public | Health check including the database (run after deploys) |
| GET | `/api/health/live` | public | Liveness only, no database (for uptime monitors, lets the database sleep) |

## Auth

| Method | Path | Needs | What it does |
|---|---|---|---|
| POST | `/api/v1/auth/login` | public | Sign in. 202 with no session when a two-factor code is needed (sets the 5-minute `__Host-empire_2fa` cookie) |
| POST | `/api/v1/auth/2fa/verify` | public (2fa cookie) | Sign-in step 2: an app code or a recovery code; creates the session |
| POST | `/api/v1/auth/2fa/enrol` | public (2fa cookie) | Forced set-up at sign-in, part 1: the key and QR code |
| POST | `/api/v1/auth/2fa/enrol/confirm` | public (2fa cookie) | Forced set-up, part 2: confirm a code, get recovery codes, sign in |
| POST | `/api/v1/auth/logout` | signed in | Sign out (revokes the session) |
| GET | `/api/v1/auth/me` | signed in | Current user, permissions and CSRF token |
| POST | `/api/v1/auth/password/forgot` | public | Email a reset link (same reply whether or not the email exists) |
| POST | `/api/v1/auth/password/reset` | public | Set a new password with a reset token |
| POST | `/api/v1/auth/password/change` | signed in | Change own password (revokes other sessions) |
| POST | `/api/v1/auth/2fa/setup` | signed in | Turn two-factor on, part 1 (needs the password) |
| POST | `/api/v1/auth/2fa/setup/confirm` | signed in | Turn two-factor on, part 2: confirm a code, get recovery codes |
| POST | `/api/v1/auth/2fa/disable` | signed in | Turn two-factor off (password and a code) |
| POST | `/api/v1/auth/2fa/recovery-codes` | signed in | New recovery codes; the old ones stop working |

## Public

Public read-only endpoints (Task 5.1). Responses set `Cache-Control: public, max-age=60, stale-while-revalidate=300` and `ETag`, returning `304 Not Modified` on matching `If-None-Match`. Error responses (404, 429) set `Cache-Control: no-store`. Enforces 120 req/min per network bucket with `Retry-After` on 429. Internal Next.js server-side renders (SSR/ISR) carrying the edge secret without a client-IP header are limited via a dedicated server bucket (`public:server`) capped at 3,000 req/min.

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/public/site` | public | Company details, nav, public flags, consent texts, active offers |
| GET | `/api/v1/public/projects` | public | Search projects (available first, then sold out; off-market hidden; FTS + trigram `q`) |
| GET | `/api/v1/public/projects/{slug}` | public | Project detail (RERA block, QR, specs, updates, gated brochure hidden) |
| GET | `/api/v1/public/projects/{slug}/configurations/{config_slug}` | public | Property (configuration) detail with project summary |
| GET | `/api/v1/public/properties` | public | Search properties (configurations) across projects (stable sort tie-breaker) |
| GET | `/api/v1/public/cities` | public | Cities with published projects and project counts |
| GET | `/api/v1/public/pages/{slug}` | public | Published page with blocks eagerly resolved (landing pages force noindex) |
| GET | `/api/v1/public/posts` | public | Blog and news articles list (filtered by category/tag) |
| GET | `/api/v1/public/posts/{slug}` | public | Article detail (author display name, body, cover image, SEO) |
| GET | `/api/v1/public/faqs` | public | FAQs (site-wide, or for one project) |
| GET | `/api/v1/public/testimonials` | public | Published testimonials (author name, quote, rating, photo; no private/audit fields) |
| GET | `/api/v1/public/redirects` | public | Active redirects (`from_path`, `to_path`, `status_code`; no ids or hit counts) |
| GET | `/api/v1/public/sitemap` | public | All public content URLs with deterministic last-modified timestamps |

## Lead intake

| Method | Path | Needs | What it does |
|---|---|---|---|
| POST | `/api/v1/public/leads` | public | Submit an enquiry (general or for a project) |
| POST | `/api/v1/public/site-visits` | public | Request a site visit (creates a lead and a visit request) |
| POST | `/api/v1/public/brochure-requests` | public | Get the brochure link (lead form first when gated) |

## AI

| Method | Path | Needs | What it does |
|---|---|---|---|
| POST | `/api/v1/ai/chat` | public · flag `chat_widget` | Chat with the site assistant (feature flag chat_widget; 404 when off) |

## Dashboard

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/dashboard` | dashboard.view | Counts that link to filtered lists, latest leads, upcoming visits, tasks |

## Projects

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/projects` | projects.read | List projects |
| POST | `/api/v1/admin/projects` | projects.write | Create project |
| GET | `/api/v1/admin/projects/{id}` | projects.read | Get project |
| PATCH | `/api/v1/admin/projects/{id}` | projects.write | Update project |
| DELETE | `/api/v1/admin/projects/{id}` | projects.delete | Delete project (a never-published draft without leads that no page block or offer names) |
| POST | `/api/v1/admin/projects/{id}/publish` | projects.publish | Publish (blocked until RERA number and QR are present) |
| POST | `/api/v1/admin/projects/{id}/unpublish` | projects.publish | Unpublish (back to draft) |
| POST | `/api/v1/admin/projects/{id}/duplicate` | projects.write | Copy as a new draft |
| GET | `/api/v1/admin/projects/{id}/towers` | projects.read | List towers |
| POST | `/api/v1/admin/projects/{id}/towers` | projects.write | Add tower |
| PATCH | `/api/v1/admin/projects/{id}/towers/{item_id}` | projects.write | Update tower |
| DELETE | `/api/v1/admin/projects/{id}/towers/{item_id}` | projects.write | Remove tower |
| PUT | `/api/v1/admin/projects/{id}/towers/order` | projects.write | Reorder towers |
| GET | `/api/v1/admin/projects/{id}/configurations` | projects.read | List configurations |
| POST | `/api/v1/admin/projects/{id}/configurations` | projects.write | Add configuration |
| PATCH | `/api/v1/admin/projects/{id}/configurations/{item_id}` | projects.write | Update configuration |
| DELETE | `/api/v1/admin/projects/{id}/configurations/{item_id}` | projects.write | Remove configuration |
| PUT | `/api/v1/admin/projects/{id}/configurations/order` | projects.write | Reorder configurations |
| GET | `/api/v1/admin/projects/{id}/specifications` | projects.read | List specifications |
| POST | `/api/v1/admin/projects/{id}/specifications` | projects.write | Add specification |
| PATCH | `/api/v1/admin/projects/{id}/specifications/{item_id}` | projects.write | Update specification |
| DELETE | `/api/v1/admin/projects/{id}/specifications/{item_id}` | projects.write | Remove specification |
| PUT | `/api/v1/admin/projects/{id}/specifications/order` | projects.write | Reorder specifications |
| GET | `/api/v1/admin/projects/{id}/location-advantages` | projects.read | List location advantages |
| POST | `/api/v1/admin/projects/{id}/location-advantages` | projects.write | Add location advantage |
| PATCH | `/api/v1/admin/projects/{id}/location-advantages/{item_id}` | projects.write | Update location advantage |
| DELETE | `/api/v1/admin/projects/{id}/location-advantages/{item_id}` | projects.write | Remove location advantage |
| PUT | `/api/v1/admin/projects/{id}/location-advantages/order` | projects.write | Reorder location advantages |
| GET | `/api/v1/admin/projects/{id}/construction-updates` | projects.read | List construction updates |
| POST | `/api/v1/admin/projects/{id}/construction-updates` | projects.write | Add construction update |
| PATCH | `/api/v1/admin/projects/{id}/construction-updates/{item_id}` | projects.write | Update construction update |
| DELETE | `/api/v1/admin/projects/{id}/construction-updates/{item_id}` | projects.write | Remove construction update |
| PUT | `/api/v1/admin/projects/{id}/construction-updates/order` | projects.write | Reorder construction updates |
| GET | `/api/v1/admin/projects/{id}/payment-plans` | projects.read | List payment plans |
| POST | `/api/v1/admin/projects/{id}/payment-plans` | projects.write | Add payment plan |
| PATCH | `/api/v1/admin/projects/{id}/payment-plans/{item_id}` | projects.write | Update payment plan |
| DELETE | `/api/v1/admin/projects/{id}/payment-plans/{item_id}` | projects.write | Remove payment plan |
| PUT | `/api/v1/admin/projects/{id}/payment-plans/order` | projects.write | Reorder payment plans |
| PUT | `/api/v1/admin/projects/{id}/amenities` | projects.write | Set the project's amenities (ordered list) |

## Catalogue

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/amenities` | projects.read | List amenities |
| POST | `/api/v1/admin/amenities` | projects.write | Create amenity |
| PATCH | `/api/v1/admin/amenities/{id}` | projects.write | Update amenity |
| DELETE | `/api/v1/admin/amenities/{id}` | projects.write | Delete amenity |
| GET | `/api/v1/admin/cities` | projects.read | List cities |
| POST | `/api/v1/admin/cities` | projects.write | Create city |
| PATCH | `/api/v1/admin/cities/{id}` | projects.write | Update city |
| DELETE | `/api/v1/admin/cities/{id}` | projects.write | Delete city |
| GET | `/api/v1/admin/localities` | projects.read | List localities |
| POST | `/api/v1/admin/localities` | projects.write | Create locality |
| PATCH | `/api/v1/admin/localities/{id}` | projects.write | Update locality |
| DELETE | `/api/v1/admin/localities/{id}` | projects.write | Delete locality |
| POST | `/api/v1/admin/maps/resolve` | projects.write | Get a pin from a Google Maps link, short link or plus code |

## Media

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/media` | media.upload | Media library |
| POST | `/api/v1/admin/media/images` | media.upload | Upload a photo through the API (magic-byte check, 10 MB limit) |
| POST | `/api/v1/admin/media/upload-signature` | media.upload | Signed parameters for a direct video/document upload to Cloudinary |
| POST | `/api/v1/admin/media/confirm` | media.upload | Save a direct upload after verifying Cloudinary's signed reply |
| PATCH | `/api/v1/admin/media/{id}` | media.upload | Rename / alt text |
| DELETE | `/api/v1/admin/media/{id}` | media.manage | Delete from library and Cloudinary (refused while attached or used by content) |
| GET | `/api/v1/admin/media/{id}/usage` | media.upload | Where a library item is used (projects, pages, posts, offers, testimonials) |
| POST | `/api/v1/admin/media-links` | media.upload | Attach media to a project, configuration, update, page or post |
| PATCH | `/api/v1/admin/media-links/{id}` | media.upload | Show/hide on website, make cover |
| DELETE | `/api/v1/admin/media-links/{id}` | media.upload | Detach (media stays in the library) |
| PUT | `/api/v1/admin/media-links/order` | media.upload | Set order for one owner+role (first = cover unless pinned) |

## Leads

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/leads` | leads.read | Lead inbox, newest first |
| POST | `/api/v1/admin/leads` | leads.update | Add a lead by hand (walk-in, phone call) |
| GET | `/api/v1/admin/leads/{id}` | leads.read | Lead detail |
| PATCH | `/api/v1/admin/leads/{id}` | leads.update | Change status, owner, details |
| DELETE | `/api/v1/admin/leads/{id}` | leads.erase | Erase personal data on request for the lead and its duplicate group; `?scope=person` also erases every lead with the same phone. Keeps anonymised stubs |
| POST | `/api/v1/admin/leads/{id}/read` | leads.read | Mark read |
| POST | `/api/v1/admin/leads/{id}/unread` | leads.read | Mark unread |
| GET | `/api/v1/admin/leads/{id}/notes` | leads.read | Notes |
| POST | `/api/v1/admin/leads/{id}/notes` | leads.update | Add note |
| GET | `/api/v1/admin/leads/{id}/activity` | leads.read | Timeline |
| GET | `/api/v1/admin/leads/export.csv` | leads.export | CSV export of the filtered list (logged in the audit log). Needs the `X-CSRF-Token` header, like a write |
| GET | `/api/v1/admin/lead-owners` | leads.read | People a lead can be assigned to |
| GET | `/api/v1/admin/reports/utm` | leads.report | Leads by source, campaign and project |
| GET | `/api/v1/admin/site-visits` | site_visits.manage | Site-visit calendar |
| PATCH | `/api/v1/admin/site-visits/{id}` | site_visits.manage | Confirm, reschedule, complete |

## Content

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/pages` | content.read | List pages |
| POST | `/api/v1/admin/pages` | content.write | Create page |
| GET | `/api/v1/admin/pages/{id}` | content.read | Get page |
| PATCH | `/api/v1/admin/pages/{id}` | content.write | Update page (scheduling and archiving a live page need content.publish; `seo` needs seo.manage; a live or scheduled legal page needs legal.publish; 409 when stale against `expected_updated_at`) |
| DELETE | `/api/v1/admin/pages/{id}` | content.write | Delete a never-published page (required pages never) |
| PUT | `/api/v1/admin/pages/{id}/blocks` | content.write | Save the page's blocks (full ordered list; 409 when stale against `expected_updated_at`) |
| POST | `/api/v1/admin/pages/{id}/publish` | content.publish | Publish (legal pages need legal.publish) |
| POST | `/api/v1/admin/pages/{id}/unpublish` | content.publish | Unpublish |
| GET | `/api/v1/admin/posts` | content.read | List posts |
| POST | `/api/v1/admin/posts` | content.write | Create post |
| GET | `/api/v1/admin/posts/{id}` | content.read | Get post |
| PATCH | `/api/v1/admin/posts/{id}` | content.write | Update post |
| DELETE | `/api/v1/admin/posts/{id}` | content.write | Delete a never-published post |
| POST | `/api/v1/admin/posts/{id}/publish` | content.publish | Publish |
| POST | `/api/v1/admin/posts/{id}/unpublish` | content.publish | Unpublish |
| GET | `/api/v1/admin/faqs` | content.read | List faqs |
| POST | `/api/v1/admin/faqs` | content.write | Create faq (showing it needs content.publish) |
| PUT | `/api/v1/admin/faqs/order` | content.write | Set the order of one FAQ list (site-wide, or one project's) |
| PATCH | `/api/v1/admin/faqs/{id}` | content.write | Update faq |
| DELETE | `/api/v1/admin/faqs/{id}` | content.write | Delete faq |
| GET | `/api/v1/admin/testimonials` | content.read | List testimonials |
| POST | `/api/v1/admin/testimonials` | content.publish | Create testimonial |
| PATCH | `/api/v1/admin/testimonials/{id}` | content.publish | Update testimonial (showing it needs a source and consent date) |
| DELETE | `/api/v1/admin/testimonials/{id}` | content.publish | Delete testimonial |

## Marketing

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/offers` | offers.manage | List offers |
| POST | `/api/v1/admin/offers` | offers.manage | Create offer |
| PATCH | `/api/v1/admin/offers/{id}` | offers.manage | Update offer |
| DELETE | `/api/v1/admin/offers/{id}` | offers.manage | Delete an offer that was never live and no page shows |

## SEO

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/redirects` | seo.manage | List redirects |
| POST | `/api/v1/admin/redirects` | seo.manage | Create redirect (loops and live addresses refused; chains collapsed to one hop) |
| PATCH | `/api/v1/admin/redirects/{id}` | seo.manage | Update redirect |
| DELETE | `/api/v1/admin/redirects/{id}` | seo.manage | Delete redirect |

## Settings

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/consent-texts` | settings.read | All versions |
| GET | `/api/v1/admin/consent-texts/current` | settings.read | Each purpose with its current version |
| POST | `/api/v1/admin/consent-texts` | legal.publish | New draft version |
| POST | `/api/v1/admin/consent-texts/{id}/publish` | legal.publish | Make this version current |
| GET | `/api/v1/admin/settings` | settings.read | All settings groups |
| PATCH | `/api/v1/admin/settings/{group}` | per group | Update one group: settings.write; tracking needs marketing.tracking, SEO defaults seo.manage, privacy the super-admin |
| GET | `/api/v1/admin/flags` | settings.read | Feature flags |
| PATCH | `/api/v1/admin/flags/{key}` | flags.manage | Switch a feature on or off |

## Integrations

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/integrations` | integrations.manage | Integration status (secrets never returned) |
| PATCH | `/api/v1/admin/integrations/{key}` | integrations.manage | Enable/disable, non-secret config |
| GET | `/api/v1/admin/webhooks` | integrations.manage | Webhook endpoints |
| POST | `/api/v1/admin/webhooks` | integrations.manage | Add endpoint (secret shown once) |
| PATCH | `/api/v1/admin/webhooks/{id}` | integrations.manage | Edit endpoint |
| DELETE | `/api/v1/admin/webhooks/{id}` | integrations.manage | Remove endpoint |
| POST | `/api/v1/admin/webhooks/{id}/rotate-secret` | integrations.manage | New signing secret (shown once) |
| POST | `/api/v1/admin/webhooks/{id}/test` | integrations.manage | Send a test event |
| GET | `/api/v1/admin/webhooks/{id}/deliveries` | integrations.manage | Delivery log |

## Users

| Method | Path | Needs | What it does |
|---|---|---|---|
| GET | `/api/v1/admin/users` | users.manage | List users |
| POST | `/api/v1/admin/users` | users.manage | Create user |
| GET | `/api/v1/admin/users/{id}` | users.manage | Get user |
| PATCH | `/api/v1/admin/users/{id}` | users.manage | Update user |
| POST | `/api/v1/admin/users/{id}/unlock` | users.manage | Clear lockout |
| POST | `/api/v1/admin/users/{id}/send-reset` | users.manage | Email a password-reset link |
| POST | `/api/v1/admin/users/{id}/revoke-sessions` | users.manage | Sign the user out everywhere |
| POST | `/api/v1/admin/users/{id}/reset-2fa` | users.manage | Remove someone's two-factor (lost phone); signs them out everywhere |
| GET | `/api/v1/admin/roles` | users.manage | Roles and their permissions |
| GET | `/api/v1/admin/permissions` | users.manage | The role table: each permission, what it allows and which roles have it |
| GET | `/api/v1/admin/audit-log` | audit.read | Audit log, newest first |

## Internal

| Method | Path | Needs | What it does |
|---|---|---|---|
| POST | `/api/v1/internal/outbox/drain` | internal key | Process pending events (called by the scheduler on free hosting) |
| POST | `/api/v1/internal/redirects/hit` | signed (`REVALIDATE_SECRET`, `redirect-hit.` prefix) | Count one redirect the website answered (task 5.6, D-047); 204 for any address |

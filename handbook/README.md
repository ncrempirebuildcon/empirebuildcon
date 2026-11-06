# Empire developer handbook

**Start here.** This folder explains how the Empire website and CMS are built, why they are built that way, and the rules for changing them. It is committed with the code. Whoever changes behaviour updates the matching page here in the same pull request.

## What the project is

- **Who it's for:** Empire ("Delivering Happiness"), a real-estate developer selling its own projects in Uttar Pradesh, with more states to come. Canonical address: `https://empirebuildcon.com`. `.in` and `.co.in` redirect to it.
- **Two parts:**
  - A **public website**: projects, homes, construction progress, blog, contact and lead forms.
  - A **staff CMS**: projects, media, leads, site visits, pages, offers, users, settings and the audit log.
- **The three jobs that matter most:**
  1. Show every project honestly: UP-RERA number and QR code, carpet area, prices and possession date.
  2. Capture leads with recorded consent.
  3. Let staff run content and leads without a developer.
- **Code:** the private GitHub repository `ncrempirebuildcon/empirebuildcon`. Ask the owner for access.
- **Stack:** Next.js (web and CMS UI), FastAPI (API and background worker), PostgreSQL and Cloudinary. Hosting starts on free tiers ([D-007](DECISIONS.md)). Versions are in [D-006](DECISIONS.md).

## Status

| Phase | What | State |
|---|---|---|
| 0 | Discovery, questions, tracker | Done |
| 1 | Architecture, data model, API contract, security plan | Done |
| 2 | Brand, design system, page and CMS templates | Done; approved by the owner on 22 Oct 2026 |
| 3 | Foundation: monorepo, CI, auth, roles, outbox | Done; merged on 22 Oct 2026 (PR #1) |
| 4 | CMS core, in five parts: projects and catalogue · media · leads · content · settings and users | Done; merged 22–26 Oct 2026 (PR #4, #5, #7, #8, #9) |
| 5 | Public website ([tasks/phase-5/PLAN.md](tasks/phase-5/PLAN.md)), built in two tracks by Claude and a developer agent ([agents/WORKFLOW.md](agents/WORKFLOW.md)) | Done; merged 1–6 Nov 2026 (PR #16 to #32) |
| Launch | Pre-launch work and go-live: QA and security (Phase 8) and go-live (Phase 9) come first ([tasks/launch/PLAN.md](tasks/launch/PLAN.md), D-050) | In progress |
| 6, 7, 10 | Marketing, AI layer, handover | After launch |

The owner keeps the live task list (a private tracker page). Ask the owner for access.

## Read in this order

1. **This page.**
2. [CONTRIBUTING.md](CONTRIBUTING.md): git, branches, push and pull, pull requests and reviews. Read it before your first commit.
3. [CODE_STYLE.md](CODE_STYLE.md): code style and the comment tags (`WHY`, `INVARIANT`, `DO NOT CHANGE`, `COMPLIANCE`, `SECURITY`).
4. [ARCHITECTURE.md](ARCHITECTURE.md): modules, data model, events, jobs and permissions.
5. [DECISIONS.md](DECISIONS.md): why things are as they are (D-001 onwards). Check it before changing anything structural.
6. [SECURITY.md](SECURITY.md): auth, sessions, uploads, secrets, personal data and backups.
7. [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md): colour tokens, type, components and accessibility.
8. [api/ENDPOINTS.md](api/ENDPOINTS.md): the API at a glance. [api/openapi-v1.yaml](api/openapi-v1.yaml) is the design contract until Phase 3 code takes over ([D-020](DECISIONS.md)).
9. [SETUP.md](SETUP.md): running everything locally (from Phase 3). [RUNBOOK.md](RUNBOOK.md): staging, production, deploys, backups and go-live (task L3).
10. [agents/WORKFLOW.md](agents/WORKFLOW.md) and [tasks/](tasks/README.md): how work is handed out, built, reviewed and merged from Phase 5.

## Repository map

```
/ (repo root)
├─ README.md            Short intro, points here
├─ AGENTS.md            Rules for AI coding agents (Claude reads it via CLAUDE.md)
├─ handbook/            ← you are here (committed)
├─ brand/
│  ├─ logo-draft/       Vector logo kit; *-noir.svg = metallic gold for dark backgrounds
│  └─ tokens/           empire-noir.json + .css — the design tokens (source for packages/ui)
├─ holding-page/        Static "coming soon" page used to check the domain
├─ apps/api/            FastAPI API, worker and admin CLI (see its README)
├─ apps/web/            Next.js website and CMS
├─ packages/ui/         Shared UI components, theme from brand/tokens
├─ packages/api-client/ Typed API client, generated from the API's OpenAPI
├─ qa/                  Playwright journeys, axe and Lighthouse
├─ .github/             CI workflow, Dependabot, pull request template
└─ docs/                Owner's private notes (brief, handover with accounts, research) — git-ignored, never committed
```

## Designs

- **Templates:** on a private design canvas (ask the owner to share it).
  - "Black & gold (dark)": the public site.
  - "Black & gold — CMS": the staff screens.
  - "Ivory & gold": reference only; it will not be built.
- **Tokens:** [`../brand/tokens/empire-noir.json`](../brand/tokens/empire-noir.json). Never hard-code a colour or radius that has a token.
- **Logos:** [`../brand/logo-draft/`](../brand/logo-draft/). Use the `-noir` files on dark backgrounds.

## Rules that never bend

These are the short versions. Details are in the linked pages.

1. **No secrets in git, ever.**
   - Use environment variables. Only `.env.example` (names, no values) is committed.
   - A leaked secret is rotated at once and reported to the owner ([SECURITY.md](SECURITY.md)).
2. **Honest content** ([D-002](DECISIONS.md), [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)):
   - Every project, property or ad view shows the UP-RERA number, the QR code and up-rera.in. Publishing is blocked without them.
   - Carpet area comes first, in sq ft and sq m.
   - Prices are shown with the note "excludes GST, stamp duty and registration".
   - No countdowns, "only N left" messages or pop-ups.
   - Nothing is invented: unknown facts are `[placeholders]`. Sample data is flagged `is_sample` and never shown on the live site.
3. **Leads and consent:**
   - Required and optional consent are separate boxes, never pre-ticked.
   - The consent text version is stored with each lead.
   - Leads are never hard-deleted; erasure goes through `leads.erase` ([ARCHITECTURE.md](ARCHITECTURE.md) §8, [SECURITY.md](SECURITY.md)).
4. **Permissions are checked in the API on every call.** Hiding a button in the UI is not security.
5. **Accessibility is WCAG 2.1 AA.** That means real buttons and labels, a visible focus ring, 44 px touch targets and colour never used as the only signal.
6. **`main` is protected.** Everything reaches it through a reviewed pull request with green CI ([CONTRIBUTING.md](CONTRIBUTING.md)). On a private repo with GitHub Free, GitHub can't enforce this, so follow it by hand (CONTRIBUTING §12, D-028).

## Glossary

| Term | Meaning |
|---|---|
| UP-RERA | Uttar Pradesh Real Estate Regulatory Authority. Every registered project has a registration number and QR code buyers can check at up-rera.in. |
| Carpet area | The RERA measure: the net usable floor area of a home, excluding external walls, service shafts, balconies and open terraces. Shown first, in sq ft and sq m. |
| BHK | Bedroom-Hall-Kitchen: "3 BHK" means three bedrooms. |
| L / Cr | Lakh (1,00,000) and crore (1,00,00,000) rupees. Display: ₹ 85 L, ₹ 1.25 Cr. Store whole rupees ([ARCHITECTURE.md](ARCHITECTURE.md) §6). |
| Configuration | One home type in a project, such as "3 BHK, 980 sq ft". The site calls these "properties" ([D-004](DECISIONS.md)). |
| DPDP Act | India's Digital Personal Data Protection Act. It drives the consent, withdrawal and erasure rules. |
| Outbox | Events are written to a database table in the same transaction as the change, then delivered by the worker ([ARCHITECTURE.md](ARCHITECTURE.md) §9). |
| Feature flag | A switch in Settings that turns a feature on or off without a deploy, for example `chat_widget`, `locale_hi`, `admin_2fa`. |
| SAMPLE | Placeholder content for design and testing. It is never shown on the live site. |

## Who decides what

- The **owner** (super-admin `admin@empirebuildcon.com`) approves designs, legal text, production releases and anything on the "owner approval" list in [CONTRIBUTING.md](CONTRIBUTING.md#owner-approval).
- Everyday code is approved by any reviewer.

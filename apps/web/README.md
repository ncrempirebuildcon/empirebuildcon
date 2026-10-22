# @empire/web

The Empire public website and the CMS user interface (Next.js 16 App Router, TypeScript, Tailwind CSS 4).

## What is here (Phase 3, Phase 4 part 1)

| Route | What |
|---|---|
| `/` | Black & gold "coming soon" holding page (`noindex`) |
| `/admin/login` | Staff sign-in (email + password; generic error; lockout message) |
| `/admin` | CMS dashboard: welcome, shortcuts and the role's permissions (counts arrive in part 3) |
| `/admin/projects` | Projects list: search and filters in the URL (`?q=&status=&publish_state=&sales_status=&city=&page=`), status chips, SAMPLE badge, paging; "+ New project" with `projects.write` |
| `/admin/projects/new` | Short create form (name, construction status, optional city) → opens the editor |
| `/admin/projects/[id]` | Project editor (board NoirCmsProject), tabs in the URL (`?tab=`): Details (basics, RERA, price), Towers, Configurations, Amenities, Specifications, Media (placeholder), Location (address, map pin from a Maps link or plus code, location advantages), Progress, Payment plans, Documents (RERA QR status, designated account), SEO. Publishing panel: blockers, Publish/Unpublish, Archive, Duplicate, Delete draft |
| `/admin/catalogue` | Cities, localities and amenities: tables with add, edit and delete |
| 404 / error | Black & gold not-found page and a "Try again" error state |
| `/robots.txt` | Disallows everything until go-live (`TODO(phase-9)`) |

The public pages arrive in Phase 5 and the other CMS screens in the later parts of Phase 4. Designs are on the design canvas; see `handbook/README.md#designs`.

### How the CMS screens work

- **Session:** every CMS page calls `requireSessionUser()` (`src/lib/session.ts`) on the server, then renders `AdminShell` around a client screen. The shell shares the user and permissions through `useAdminSession()`; menu items and buttons a role can't use are hidden, and the API checks every call anyway.
- **API calls:** only through the generated client (`@empire/api-client`) via `call()` in `src/lib/api.ts`, which returns the data or throws `ProblemError`, and sends the user to sign in on a 401. Writes carry the CSRF token the shell sets from `/auth/me`. Types come from `Schema<"ProjectAdmin">` and friends, never hand-written.
- **Errors:** `src/lib/problems.ts` turns problem+json into a page message and field messages keyed by the dotted field path (`price.min_inr`), shown next to their fields.
- **Saving in the editor:** the project's own fields save together with "Save draft" (PATCH); fields typed while a save runs keep the newer text and stay unsaved. Towers, configurations, specifications, location advantages, construction updates and payment plans save item by item (add, edit, remove, Move up/Move down); an item form is locked while it saves, and opening another item while one has unsaved edits asks "Discard your changes?". Amenities save with "Save amenities".
- **Unsaved changes:** leaving by a link, closing the tab or signing out asks first (`useUnsavedChanges`); Publish and Duplicate wait until the changes are saved.
- **Off market on a live project:** without `projects.publish`, a published project can't be moved into or out of "Off market" (the API refuses it too), and the Sales status field says why.
- **Map pin:** "Get pin" stores the normalised plus code from the API (never the place name typed after it) and the link only when a link was pasted; both are shown with Clear buttons, and typing coordinates by hand clears them.
- **Phones:** no CMS page scrolls sideways at 390 px; wide tables scroll inside their own region (`qa/specs/responsive-cms.spec.ts`).
- **Media:** uploads, floor plans, the RERA QR upload and share images show "Media manager arrives in the next update" until part 2 (`TODO(phase-4)`). The draggable map comes with the public site (`TODO(phase-5)`).

## How it fits together

- The browser only calls `/api/*` on this site; `next.config.ts` rewrites those calls to `API_ORIGIN` (handbook/ARCHITECTURE.md §3). `skipTrailingSlashRedirect` stays on (`DO NOT CHANGE`).
- Security headers are set in `next.config.ts` (handbook/SECURITY.md §4). The nonce-based CSP comes in Phase 5.
- CMS pages check the session on the server (`src/lib/session.ts`) and are never cached.
- Styling uses only the generated tokens from `@empire/ui` (`bg-noir-900`, `text-gold-300`, `rounded-card`, `font-display`…). Fonts are self-hosted from npm (`@fontsource`).

## Commands

```bash
pnpm --filter @empire/web dev        # http://localhost:3000 (start the API on :8000 too)
pnpm --filter @empire/web build
pnpm --filter @empire/web start
pnpm --filter @empire/web lint
pnpm --filter @empire/web typecheck
```

Environment (see `.env.example` at the repo root): `API_ORIGIN`, `SITE_URL`.

## Rules

- **Tokens only:** never hard-code a colour, radius or font that has a token.
- **No facts in code:** prices, RERA numbers, counts and company details come from the API/CMS. Unknown facts are `[placeholders]`.
- **Accessibility (WCAG 2.1 AA):** real buttons and links, a visible label on every field, a focus ring, 44 px touch targets, and text on every status. Reordering always has Move up/Move down buttons; confirmations use `ConfirmDialog`, never `confirm()`. Links inside sentences are underlined.
- `dangerouslySetInnerHTML` is banned by lint except in `src/components/JsonLd.tsx` (`SECURITY`).

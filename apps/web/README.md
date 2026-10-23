# @empire/web

The Empire public website and the CMS user interface (Next.js 16 App Router, TypeScript, Tailwind CSS 4).

## What is here (Phase 3, Phase 4 parts 1 and 2)

| Route | What |
|---|---|
| `/` | Black & gold "coming soon" holding page (`noindex`) |
| `/admin/login` | Staff sign-in (email + password; generic error; lockout message) |
| `/admin` | CMS dashboard: welcome, shortcuts and the role's permissions (counts arrive in part 3) |
| `/admin/projects` | Projects list: search and filters in the URL (`?q=&status=&publish_state=&sales_status=&city=&page=`), status chips, SAMPLE badge, paging; "+ New project" with `projects.write` |
| `/admin/projects/new` | Short create form (name, construction status, optional city) → opens the editor |
| `/admin/projects/[id]` | Project editor (board NoirCmsProject), tabs in the URL (`?tab=`): Details (basics, RERA, price), Towers, Configurations (with each one's floor plan), Amenities, Specifications, Media (media manager), Location (address, map pin from a Maps link or plus code, location advantages), Progress (with each update's photos), Payment plans, Documents (RERA QR code, brochure and "brochure gated", documents, designated account), SEO (with the share image). Publishing panel: blockers, Publish/Unpublish, Archive, Duplicate, Delete draft |
| `/admin/catalogue` | Cities, localities and amenities: tables with add, edit and delete |
| `/admin/media` | Media library: every photo, video and document as a grid or a list; search, type and "not attached" filters and the view in the URL (`?q=&kind=&unattached=true&view=list&page=`); rename, alt text and honest label (a neutral "No label" where none is set: QR codes, plans and share images need none); "Delete from library" only with `media.manage` and only when the file is attached to nothing (the others say where they are used); SAMPLE placeholders carry the SAMPLE chip |
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
- **Media manager** (`src/components/admin/media/`, `src/lib/media/`, ARCHITECTURE §12):
  - One drop zone (a real button with a file chooser; dropping files is a bonus) sends each file to the right list by type: photos to the gallery, videos, documents. Photos, Videos and Documents show their counts; each item has its order number, the cover star (photos), a HIDDEN badge, its honest label (artist's impression / actual photo / progress photo with the month), a "Show on website" switch, Move up/Move down (mouse users can also drag), "Edit details" (title, alt text, label and month, in a dialog) and "Remove from project" (the file stays in the library).
  - **Honest labels first:** photos dropped on the Media tab wait for one question, "What are these photos?" (artist's impression, actual photo, or progress photo with its month; nothing pre-selected). The answer is sent with the batch (`ImageUpload.label`/`label_month`), so they arrive shown. The API keeps an unlabelled gallery photo hidden: such a photo says "Hidden until labelled", its switch is disabled with the reason, and "Add label" opens its details. Progress photos added to a construction update are labelled with the update's month.
  - Files are checked in the browser before anything is sent (`lib/media/files.ts`: JPG, PNG, WebP, AVIF ≤ 10 MB; MP4, MOV, WebM ≤ 100 MB; PDF, DOC, DOCX, PPT, PPTX ≤ 10 MB; never SVG, HEIC or GIF). The API checks everything again.
  - **Photos** are re-encoded in the browser (`lib/media/resize.ts`), which also drops EXIF/GPS data, then sent to `POST /admin/media/images` with an XHR so progress shows: photos at a 2560 px long edge as WebP (else JPEG) at 0.85; the RERA QR as lossless PNG at 1200 px; floor plans as lossless WebP (else PNG). Smaller sizes are tried when a result is over 10 MB.
  - **Videos and documents** go straight to the store: `upload-signature` → XHR POST of the file with exactly the signed `fields` to `upload_url` → `confirm` with the store's reply unmodified (it attaches the file too). In development and tests the API's fake store answers like Cloudinary on `/api/v1/dev-media/…`, so the same code runs.
  - Uploads run one at a time with a progress bar (`role="progressbar"`), Cancel while the file is being sent, and Dismiss for a refusal; start, finish and failures are announced in a polite live region. Once every byte is sent the row says "Saving…" and Cancel goes away (the server finishes on its own); a Cancel that races the end re-reads the owner, so the list shows what was really saved. Running uploads count as unsaved changes for the leave warning; editing a construction update keeps its photo uploads running.
  - "Show on website" and the cover star save one change at a time: a switch flipped while another saves shows "Saving…" and waits its turn.
  - Single places replace in one step: the RERA QR code (Documents; required to publish; a live project's QR can be replaced, never removed or hidden), the brochure (one PDF), each configuration's floor plan (image or PDF), the share image (SEO; pick a project photo or upload one, saved with Save draft as `seo.og_image_id`).
  - Media needs `media.upload`, not `projects.write` (marketing manages media without editing facts); deleting from the library needs `media.manage`.
  - Previews use plain `<img>` with the store's thumbnail URLs and the item's alt text (else its title); QR codes and floor plans sit on an ivory tile. The public image loader comes in Phase 5 (`TODO(phase-5)`).
- **Request size:** `next.config.ts` lets the `/api` proxy pass request bodies up to the API's 10 MB photo cap plus 64 KB (`experimental.proxyClientMaxBodySize`); without it Next.js cuts bodies at 10 MB. With the fake store, direct uploads also pass through this proxy, so locally a video above about 10 MB is refused; test big files against Cloudinary.
- **Map:** the draggable map comes with the public site (`TODO(phase-5)`).

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

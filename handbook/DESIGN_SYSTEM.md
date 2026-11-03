# Empire design system: Black & gold

**Phase 2** · 20 Oct 2026 · Source of truth for the website and CMS look. It replaces the colour table in the owner's project brief (§7). Decisions: [DECISIONS.md](DECISIONS.md) D-023 (theme approved), D-024 (scope). The machine-readable copy is `../brand/tokens/empire-noir.json`, with `empire-noir.css` alongside it. Phase 3 builds the Tailwind theme from these files.

Design canvas: https://claude.ai/artifact/7cA6o6WyALwUfb17n6W7zY. It has three pages: "Black & gold (dark)" for the public site, "Black & gold — CMS", and "Ivory & gold (light)", which is kept for reference only.

---

## 1. Principles

1. **Gold on black, like the logo.** The page is a warm near-black, never pure black. Text is ivory, never pure white. Gold marks what matters: the logo, the main headline, prices, buttons and active states.
2. **Facts before decoration.** Every project or property block shows the UP-RERA number, QR code, carpet area (sq ft and sq m), price and possession together.
3. **Calm, not pushy.** There are no pop-ups, countdowns, "only N left" messages or auto-playing sound. Motion is limited to fades.
4. **Readable at night on a phone.** Body text is warm ivory at 16 px or larger with high contrast, and every touch target is at least 44 px. Links inside running text are the one exception (WCAG 2.5.8); short links get `min-w-11` as well. A link that must not move the layout may use `-my-2.5 py-2.5` (card titles) only where nothing interactive sits within that reach; a checkbox label is padded to 44 px without negative margins, so it never covers a neighbour (a tap meant for something else must never tick a consent box). `qa/specs/public-pass.spec.ts` checks every public route.

## 2. Colour tokens

| Token | Hex | Use |
|---|---|---|
| `noir-900` | `#0E0C0A` | Page background |
| `noir-950` | `#0A0908` | Footer, CMS sidebar |
| `noir-800` | `#171411` | Cards, bands, panels |
| `noir-700` | `#1F1A15` | Inputs, raised tiles, skeletons |
| `line` | `#2A241D` | Dividers, table rules, quiet card borders |
| `line-strong` | `#3A3127` | Icon-button outlines, segmented-control frames (decorative) |
| `field-line` | `#7A6C5B` | **Input, select and textarea borders** (3:1 or better, see §9) |
| `ivory` | `#F5EEDF` | Headings, strong text |
| `body` | `#D9CFBF` | Body text |
| `muted` | `#A89A86` | Secondary text, captions |
| `gold-300` | `#F1D990` | Prices, small gold text, active nav text, focus ring |
| `gold-400` | `#E2B65A` | Links, icons, eyebrows |
| `gold-500` | `#D9A441` | Primary buttons (text `noir-900`), accents, active tab fill |
| `gold-700` | `#B07A2A` | Hairlines and the gradient end only, not text |
| `gold-line` | `rgba(217,164,65,0.28)` | Card borders |
| `gold-line-strong` | `rgba(217,164,65,0.45)` | Emphasis borders (forms, featured panels) |
| `palm` | `#B6D9A6` | Success, "Ready to move", WhatsApp text |
| `palm-line` | `#5E8A4E` | Success borders |
| `palm-bg` | `#1F2A1B` | WhatsApp button background |
| `danger` | `#E3907E` | Errors, the SAMPLE label |
| `danger-bg` | `#5A2A20` | "Sold out" chip (text `#F8DCD3`) |
| `ivory-tile` | `#FAF7F1` | Background behind QR codes and floor plans |

**Metallic gradient**, used for the logo and the single H1 of each page only:
`linear-gradient(180deg, #F8E7B0 0%, #E2B65A 55%, #C08A2E 100%)` as text fill, with a solid `#E2B65A` fallback colour.

**Gold hairline:** `#B07A2A → #E2B65A`, for progress bars and dividers.

## 3. Typography

| Role | Font | Size (desktop / mobile) | Weight | Notes |
|---|---|---|---|---|
| Display H1 | Cinzel | 58–74 / 36–38 px | 600 | Metallic gradient, one per page, `text-wrap: balance` |
| Section H2 | Cinzel | 34 / 26 px | 600 | Ivory |
| Card title H3 | Cinzel or Manrope | 21–24 / 18–21 px | 600 / 700 | Ivory |
| Eyebrow | Cinzel | 13 / 12 px | 600 | Letter-spacing 0.28em, `gold-400`, uppercase |
| Lede | Manrope | 18–19 / 15–16 px | 400 | Body colour |
| Body | Manrope | 16 px | 400 | Line height 1.55–1.6 |
| Small | Manrope | 13–14 px | 500–600 | Muted colour from 13 px |
| Price | Manrope | 20–22 px | 800 | `gold-300`, tabular numbers |
| CMS body / table | Manrope | 15 / 14 px | 400–600 | Table headers 12 px, letter-spacing 0.08em, `gold-400` |

Formats:
- Money: ₹ 85 L · ₹ 1.25 Cr · ₹ 12,34,567 (Indian grouping).
- Area: carpet area first, "980 sq ft · 91.0 sq m" (sq m = sq ft × 0.092903, one decimal).
- Dates: 30 Sep 2026.

## 4. Spacing, layout, radii, borders

- **Spacing scale (px):** 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 56 · 72. Sections are spaced 56–72 px apart on desktop and 24–32 px on mobile.
- **Containers:** content up to 1280 px with 32 px side gutters on desktop; 16 px gutters on mobile; long text up to about 42em per line.
- **Radii:**
  - Pills (buttons, chips): 999 px.
  - Large card: 22 px. Card: 18 px. Tile: 14 px. Input: 12 px. Tag: 8 px.
  - **Arch:** `999px 999px 10px 10px` on card images, `999px 28px 18px 18px` on the hero.
- **Borders over shadows:** dark surfaces use 1 px borders (`gold-line` or `line`), not drop shadows. Overlays like the lightbox use `rgba(14,12,10,0.88)`.
- **Focus:** 2 px solid `gold-300` outline with a 2 px offset on every interactive element. Never removed.

## 5. Motifs

- **Arch:** on hero and project images, plus an arch-shaped gold outline on the home hero.
- **✦ hairline:** a gold hairline with a four-point star in the middle, used as a section divider.
- **Rising towers:** tower-wise progress bars with the gold gradient, labelled with a percentage and a date.
- **Palm-leaf line icons:** for amenities and landscape.

## 6. Iconography

- Line icons on a 24 px grid, stroke 1.3–1.8, round joins, `gold-400` on dark backgrounds.
- Icon-only buttons always have an `aria-label`. Icons sit next to text labels in the CMS nav and amenities lists.

## 7. Imagery

- Dusk and night photography suits this theme best. Daytime photos look flat on black, so the shoot brief should ask for blue-hour and night shots of the towers, clubhouse and pool, plus daylight interiors.
- Every image is labelled for what it is: artist's impression, actual photo, sample flat, or progress photo with its date.
- QR codes and floor plans always sit on an `ivory-tile` so phones can scan them and plans stay readable.

## 8. Components (see the "Components & states" board)

| Component | Rules |
|---|---|
| Buttons | Primary: `gold-500` fill with `noir-900` text, weight 800. Secondary: 1 px `gold-500` outline with `gold-300` text. Tertiary: `gold-400` text link. WhatsApp: `palm-bg` with `palm` text. Min height 44 px. Loading shows a spinner and keeps the label. Disabled is shown at 45% opacity and announced with `aria-disabled`. |
| Inputs | `noir-700` fill, 1 px `field-line` border, 12 px radius, 16 px text (no zoom on iOS), visible label above. Error state: `danger` border plus a message under the field. |
| Lead form | Name plus mobile (Indian numbers for now; the hint points visitors outside India to WhatsApp or email, D-043). Two separate consent boxes, never pre-ticked: the required one with the current text's label and "Read the full consent text", and the optional marketing one. Then "Privacy notice · you can withdraw consent any time". OTP, if used, comes only after submit. The thank-you state shows the reference (and the brochure link for a brochure request). Errors appear in a live region that receives focus, and field errors sit under their fields; nothing typed is lost. Without JavaScript, or with no current consent text, the visitor sees call and WhatsApp links instead of the form. Built in `apps/web/src/components/leads/` (task 5.4). |
| Chips | Under construction: gold outline. Ready: palm outline. Sold out: `danger-bg`. SAMPLE: `danger` text. Chips always carry a text label. |
| Project card | Arched image, status chip, name, locality, configuration, carpet area, price, possession, UP-RERA number with a Verify link, "View project" plus a WhatsApp button. |
| Property card | Configuration title, project, carpet area (sq ft · sq m), price from, possession, status, RERA number. |
| RERA badge | QR on an ivory tile, registration number, "Verify on up-rera.in". Required on every project, property and campaign view. |
| Key-facts strip | Price, homes, carpet area, possession, towers, RERA/QR in one row of tiles. |
| Sticky mobile bar | Call · WhatsApp · Enquire, with WhatsApp given the same weight as Call. Enquire is the gold primary button. |
| Gallery / lightbox | Swipe on mobile; the lightbox shows a counter, previous/next buttons, a close button and the image label. |
| Map | Loads on tap (performance), dark style, pin pop-up with the project name and "Get directions". |
| Progress timeline | Dated entries, tower bars, photo with date. |
| FAQ | A button with `aria-expanded`; one item open at a time. |
| Offer banner | Offer name, details, "Valid [start] – [end]", T&C link. No timers. |
| States | Empty (honest message plus a next step), loading skeletons in `noir-700` (no shimmer when reduced motion is on), error ("Couldn't load" plus Try again), toasts with `role="status"`. |
| Chat slot | A reserved bubble bottom-right, off until Phase 7 (feature flag). |
| CMS shell | 248 px `noir-950` sidebar with a gold active bar, 64 px top bar with search, sample-data warning strip, cards in `noir-800`. Stage chips: New, Contacted, Site visit, Negotiation, Booked, Lost, all text-labelled. |
| CMS form kit (`@empire/ui`) | `TextField`, `Select`, `Textarea` with a character count, and `NumberField` (whole rupees with Indian grouping; never `type=number`). They share one label, hint and error layout. Also: `Tabs`, `Table` (real headers), `ConfirmDialog` (native `<dialog>`, focus starts on Cancel), `ReorderList` with Move up/Move down buttons and an `aria-live` announcement (drag is optional, the buttons are required), and `Skeleton`. `Button` has a `danger` variant. `Chip` adds `upcoming`, `available` and `offMarket`. Details in `packages/ui/README.md`. |
| Media kit (`@empire/ui`) | `FileDropZone`/`FileButton`: a real button with a file chooser, where drag and drop is an extra. `ProgressBar` (`role="progressbar"`), `Switch` ("Show on website"), `SegmentedControl` (Photos/Videos/Documents) and `Dialog`. Media cards show the order number, a cover star, a HIDDEN badge and an honest label (artist's impression / actual photo / progress photo with month). Every `<img>` uses the item's alt text, else its title. |
| Leads kit (`@empire/ui`) | Stage chips `stageNew` … `stageLost` (always text-labelled), `Table` `rowClassName` (unread rows are bold with a gold dot plus the hidden text "Unread:"). Format helpers: `maskPhone` (`+91 98xxxxxx10`, used in lists, cards and the dashboard; the full number only on the lead detail), `formatPhone`, `telHref`, `whatsappHref` (mobiles only), India-time calendar helpers and `formatAge`. Stage changes use a "Move to" select, never drag only, and are announced. |
| Content kit (`@empire/ui`) | `FormattedText` renders WhatsApp-style text (`*bold*`, `_italic_`, `- ` bullets nested by two spaces, at most four levels, and paragraphs) as React elements with our own parser; HTML-looking text shows as text. `FormattedTextEditor` is a textarea with the formatting hint, a live preview and an "n / limit characters" count. `Checkbox` takes a linked `hint`. In the CMS, the block editor moves blocks with Move up/Move down buttons (no drag), announces every move, show/hide and delete, and keeps focus on the moved block. Section sub-navigation (Offers, Blog posts, FAQs, Testimonials, Redirects) is links with `aria-current`, not ARIA tabs, because each section has its own address. |
| Account kit (`@empire/ui`) | `PasswordField` (show/hide toggle, policy messages at the field), `OneTimeCodeField` (`autocomplete="one-time-code"`, `inputmode="numeric"`, one field, not six boxes), `CodeList` (recovery codes spelled out for screen readers, with copy and download as text) and vertical `Tabs` for the Settings sections. The two-factor QR image always has the typed key as its alternative. |
| Public shell (`apps/web`) | `Header` (brand logo, ordered nav items from `/public/site`, Book a site visit CTA, skip link `#main-content`, mobile slide-over drawer with keyboard focus trap, Esc to close, focus restoration), `Footer` (UP-RERA disclaimer, up-rera.in portal link, official channels notice `empirebuildcon.com`, social links with minimum 44 px tap targets, legal nav, copyright year), `MobileActionBar` (sticky on mobile viewports with equal Call and WhatsApp actions, WhatsApp `{page}` replacement, Enquire CTA), `OfferBanner` (first active banner offer, session dismissible via `sessionStorage`, date validity range), `SampleDataRibbon` (amber warning ribbon when `has_sample` is true on public site in non-production), and `PublicImage` (wraps `next/image` with Cloudinary custom loader and honest labels). |
| Catalogue kit (`apps/web/src/components/catalogue`, task 5.3) | `ReraBlock` (panel: QR on `ivory-tile`, number, tower/phase numbers that differ, "Verify on up-rera.in" opening in a new tab; `line` variant for cards; never hides itself), `PriceText` (the API's display text in `gold-300` with the tax note under it; "Price on request" never shows a figure), `AreaText` (carpet first, both units, basis in brackets), status chips (Under construction, Ready to move, Upcoming, Sold out, SAMPLE), `ProjectCard` and `PropertyCard` (arched image with its honest label; the title is the link, so the external Verify link never nests in it), `FilterForm` (a plain GET form, 44 px controls with visible labels), `Pager` (links, `aria-current="page"`), `Breadcrumbs`, the project sections (home types table with a caption, gallery, videos with `preload="none"`, amenities, specifications, location advantages, tower progress bars with `role="progressbar"`, dated updates, payment plans, documents, FAQs in native `<details>`), and `ProjectMap` (button after hydration only; dark style by a filter on OpenStreetMap tiles; attribution always visible). |
| Page blocks (`apps/web/src/components/blocks`, task 5.5a) | One server component per block type, drawn with the kits above. **Hero:** a leading hero is the page's h1 (metallic), with an arched image and up to two buttons. **Rich text and columns:** `FormattedText`. **Image and gallery:** `PublicImage` with labels. **Video:** a library video, or a "Watch … on YouTube/Vimeo" link (no embed before consent). **Grids:** the catalogue cards. **CTA:** a panel with one gold button. **Lead form:** the 5.4 form, with the project's RERA block (number, QR, up-rera.in) when the block names a project; it sends the source staff chose, except that a site-visit or brochure block without a project asks a plain question and sends `contact_form`. **Stats:** big gold numbers, each with "As of … · Source: …". **Testimonials:** quote cards with the name and detail as entered. **Offer:** a panel with the terms line and link, no timer. **Map:** the project's RERA block, the address, directions and the map on tap. **Steps:** numbered tiles. **Divider:** the ✦ hairline. A legal page with draft text shows a red DRAFT note above the title, and its version under the title (or under its hero). Step and column titles are h3 under a block heading, h2 without one. |

## 9. Accessibility review (WCAG 2.1 AA)

Contrast ratios were computed with the WCAG formula. 4.5:1 is required for normal text, 3:1 for large text and UI boundaries.

| Pair | On `noir-900` | On `noir-800` | On `noir-700` |
|---|---|---|---|
| Ivory headings `#F5EEDF` | 16.9 | 15.9 | 14.9 |
| Body `#D9CFBF` | 12.7 | 11.9 | 11.2 |
| Muted `#A89A86` | 7.1 | 6.7 | 6.3 |
| Gold-300 `#F1D990` | 14.0 | 13.2 | 12.4 |
| Gold-400 links `#E2B65A` | 10.3 | 9.7 | 9.1 |
| Gold-500 `#D9A441` | 8.7 | 8.2 | 7.7 |
| Palm `#B6D9A6` | 12.5 | 11.8 | 11.1 |
| Danger `#E3907E` | 8.0 | 7.5 | 7.0 |
| **Field border `#7A6C5B`** (UI, needs 3:1) | 3.8 | 3.6 | 3.4 |

Other pairs:
- Black on gold buttons: 8.7.
- WhatsApp text on its background: 9.6.
- Sold-out chip: 9.1. Booked chip: 9.9. Lost chip: 11.6.
- Gold-300 on the 18% gold tint (active filters): 9.5.
- Ink on an ivory tile: 14.7.

**Found and fixed in this review**
- Input borders first used `#3A3127`, which is only 1.4–1.5:1 against the page, so fields were hard to see. All inputs, selects and textareas now use `field-line #7A6C5B`.
- Several search and password fields removed the browser focus outline (`outline: none`). That is now removed everywhere, and every board has a 2 px `gold-300` focus ring on `:focus-visible`.
- Two small text marks used `#6B5E4E` (2.7–3.1:1): a disabled pager arrow and the "—" in the permission matrix. They now use `muted`.
- `gold-700` is kept for hairlines and never used for text, because it is only 4.6–5.3:1 and dims at small sizes.
- Muted text is never used on gold. It is at least 6.3:1, so it passes AA at any size, but body copy stays at 13 px or larger.
- Every text colour on every board was scanned: all pass 4.5:1 on all three dark surfaces. Black text appears only on gold or ivory.

**Independent content review (20 Oct)**
A separate reviewer checked all 30 boards for invented facts, RERA display, urgency wording and consent rules. Fixes made:
- The unverifiable "Every Empire project is registered with UP-RERA" now reads "Every project on this site shows its UP-RERA registration number and QR code".
- Price notes now say "exclude GST, stamp duty and registration" everywhere prices appear.
- The RERA number was added to the map list, the progress teaser, the enquiry sheet, the offer banner and the map pop-up.
- Nothing is pre-selected or pre-ticked any more, and optional site-visit fields are labelled "(optional)".
- An illustration tagged "Actual photo" in the media manager is now tagged "Artist's impression".
- The project disclaimer no longer says prices are registered with UP-RERA.

**Built into the templates**
- Real `<button>`/`<a>` elements throughout.
- `aria-current` on the active nav item; `aria-pressed`, `aria-checked` or `aria-selected` on toggles and tabs; `aria-expanded` on FAQs.
- A visible label on every field, and `aria-label` on icon-only buttons.
- 44 px minimum touch targets on mobile.
- Alt text on every image, with labels that say whether it is a render or a photo.
- Colour is never the only signal: chips and stages carry text.
- No content that flashes or moves on its own.

**To verify when it is built (Phase 5 and Phase 8)**
- axe and Lighthouse accessibility at 90 or above.
- Keyboard-only walk-through of every form, the filters and the lightbox.
- Screen-reader check (NVDA and TalkBack) of the lead form and the consent boxes.
- Real-device checks at night brightness.
- `prefers-reduced-motion` turns off fades and skeleton shimmer.
- Hindi text rendering, if that language is switched on.

## 10. Motion

- Fades and gentle reveals only: 150–200 ms, ease-out, opacity plus at most 8 px of translation.
- No parallax, no auto-advancing carousels.
- Everything is off under `prefers-reduced-motion: reduce`.

## 11. Board index

**Public (Black & gold page)**
- NoirHome, NoirBrand, NoirProjects, NoirProject, NoirMobileHome, NoirMobileProject.
- NoirContact, NoirMobileEnquiry, NoirAbout, Noir404.
- NoirProperties, NoirProperty, NoirMobileProperty.
- NoirBlog, NoirArticle, NoirLegal.
- NoirCampaign, NoirMobileCampaign, NoirComponents.

**CMS (Black & gold — CMS page)**
- NoirCmsLogin, NoirCmsDashboard, NoirCmsLeads, NoirCmsLead, NoirCmsVisits.
- NoirCmsProject (project editor, configurations and media manager).
- NoirCmsPage, NoirCmsContent, NoirCmsUsers, NoirCmsSettings, NoirCmsAudit.

## 12. Notes from the template build

- Media upload limits on the project editor follow ARCHITECTURE.md §12: photos and documents up to 10 MB, video up to 100 MB.
- Lead forms collect only name and mobile, so lead detail shows budget and configuration interest as "from call notes", filled in by sales.
- Feature flags shown in Settings: `locale_hi`, `admin_2fa`, `captcha` and `chat_widget` can be switched. `listings` and `unit_inventory` are locked because they are not built.
- Only one 3 BHK floor-plan drawing exists in the samples. The 3 BHK Premium tab reuses it with a caption saying its own drawing is to come.


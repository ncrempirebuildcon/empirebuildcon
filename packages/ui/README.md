# @empire/ui

Black & gold design system for the Empire website and CMS: generated design tokens, a few accessible React components, and money, area, phone and India-time display helpers.

| Path | What |
|---|---|
| `src/theme.css` | **Generated** Tailwind v4 `@theme` from `brand/tokens/empire-noir.json`. Never edit by hand. |
| `src/tokens.ts` | **Generated** typed copy of the same tokens |
| `src/components/` | `Button`, `TextField`, `Checkbox`, `Chip`, `Alert`, and for the CMS: `Select`, `Textarea` (+ `CharacterCount`), `NumberField`, `Tabs`/`TabPanel`, `Table`, `ConfirmDialog`, `Dialog`, `ReorderList`/`ReorderButtons` (+ `moveItem`, `LiveRegion`), `Skeleton`, and for the media manager: `Switch`, `ProgressBar`, `FileDropZone`/`FileButton`, `SegmentedControl` |
| `src/format/` | `formatInr`, `formatInrRange`, `formatInrFull`, `sqftToSqm`, `sqftToSqmStored`, `sqmToSqft`, `formatArea`, `formatAreaRange`; phones: `maskPhone` (`+91 98xxxxxx10`), `formatPhone` (`+91 98765 43210`), `telHref`, `whatsappHref` (mobiles only), `isIndianMobile`; India time: `istDate`, `istTime`, `istToIso` (date + time typed in IST → UTC), `istToday`, `addDays`, `startOfWeek` (Monday), `weekdayIndex`, `isCalendarDate`, `formatClock` (`11:00 am`), `formatAge` (`8 min`, `3 h`, `2 d`) |

### Components

| Component | Use it for | Notes |
|---|---|---|
| `Button` | Actions | Variants `primary`, `secondary`, `tertiary`, `whatsapp`, `danger` (outline, for archive/delete). `loading` keeps the label; `disabled` uses `aria-disabled` so the button stays focusable. |
| `TextField`, `Select`, `Textarea` | Labelled form fields | Label above, `hint` and `error` linked with `aria-describedby`, `field-line` border, 16 px text. `Select` is a native `<select>`. |
| `CharacterCount` | Soft length limits (SEO) | "56 / 60 characters · good" / "· too long" in words, not only colour. |
| `NumberField` | Rupees, areas, percentages, coordinates | `value: number | null` + `onValueChange`. Whole numbers by default with Indian grouping when idle (78,00,000); `decimals`, `allowNegative`, `prefix`/`suffix`. Text input with `inputMode`, never `type="number"`. |
| `Tabs` + `TabPanel` | Sectioned editors | WAI-ARIA tabs with automatic activation: arrows, Home and End. Hidden panels stay mounted so their state is kept. Same `idPrefix` on both. |
| `Table` | Data tables | Caption (visible or screen-reader only), `scope`d headers, optional row-header column, `empty` message, focusable scroll region, `rowClassName` for one row's look (e.g. bold unread leads; pair it with a text cue). |
| `ConfirmDialog` | Delete, archive, unpublish | Native `<dialog>` with `showModal()`: focus trapped, Cancel focused first, Escape cancels, blocked while `busy`; shows an `error`. Never use `confirm()`. |
| `ReorderList`, `ReorderButtons`, `moveItem`, `LiveRegion` | Ordering | Move up/Move down buttons (`aria-disabled` at the ends so focus stays) and a polite announcement "Tower B moved to position 1 of 2." Drag handles may be added on top, never instead. |
| `Dialog` | Short forms in a modal ("Photo details") | Native `<dialog>` with `showModal()`, labelled by its title, first field focused, Escape closes (not while `busy`), Enter submits. Yes/no questions use `ConfirmDialog`. |
| `Switch` | On/off that saves at once ("Show on website · Shown") | `<button role="switch">` with `aria-checked`, the state also in words, `context` adds the item's name for screen readers only; `busy`/`disabled` use `aria-disabled`. 44 px tall. |
| `ProgressBar` | Upload progress | `role="progressbar"` with `aria-valuenow` 0–100, a name and `aria-valuetext`; `value={null}` is indeterminate. Gold hairline gradient. Announce start/end in a `LiveRegion`, not every percent. |
| `FileDropZone`, `FileButton` | Choosing files | A real button opens the file chooser (hidden `<input type="file">`), so keyboard and screen-reader users never drag. The drop zone also takes dropped files; its hint is linked with `aria-describedby`. `accept` only steers the chooser: callers still check type and size. |
| `SegmentedControl` | A few views of one list ("Photos · 8 / Videos · 1") | `role="radiogroup"` with `role="radio"` pills, roving tab stop, arrow keys, Home/End. |
| `Chip` | Status labels | Always text. Variants include `upcoming`, `ongoing`, `completed`, `available`, `soldOut`, `offMarket`, `draft`, `published`, `archived`, `sample`, and the lead pipeline stages `stageNew`, `stageContacted`, `stageSiteVisit`, `stageNegotiation`, `stageBooked`, `stageLost` (the `stage-*` tokens). |
| `Skeleton` | Loading placeholders | `noir-700`, no pulse with reduced motion; decorative (pair with `aria-busy` and a text). |

## Commands

```bash
pnpm --filter @empire/ui tokens        # regenerate theme.css + tokens.ts after changing the JSON
pnpm --filter @empire/ui tokens:check  # CI: fails if the generated files are stale
pnpm --filter @empire/ui test          # unit tests (Vitest + Testing Library)
pnpm --filter @empire/ui lint
pnpm --filter @empire/ui typecheck
```

## Rules

- **Tokens only.** Use the Tailwind classes generated from the tokens (`bg-noir-900`, `text-gold-300`, `rounded-card`, `font-display`). Never hard-code a colour or radius that has a token (handbook/CODE_STYLE.md §3).
- **No facts in components.** Prices, RERA numbers and counts come from the CMS through props.
- **Phones and time:** lists show `maskPhone`; only a single lead's page shows `formatPhone` (SECURITY.md §8). India time uses a fixed +05:30 (no daylight saving), so the helpers behave the same on every machine; `test/leads-format.test.ts` holds the vectors.
- **Area storage:** send square metres from `sqftToSqmStored` (4 decimals, round-trips to the same whole sq ft); show sq m with `sqftToSqm` (1 decimal). `test/format.test.ts` holds the vectors the API's Python twin copies; storage tests live in `test/area-storage.test.ts`.
- **Accessibility (WCAG 2.1 AA):** visible labels, `aria-describedby` for hints and errors, 44 px touch targets, a visible focus ring, and text on every status chip. Consent checkboxes are never pre-ticked (`COMPLIANCE`).
- Apps consume this package as TypeScript source (`transpilePackages` in Next.js) and must add `@source` for `packages/ui/src` in their Tailwind CSS so the component classes are generated.

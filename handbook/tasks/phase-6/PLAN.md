# Phase 6 · Marketing tools (plan)

The owner asked on 6 Nov 2026 to start Phase 6 while the company's launch forms are out, so the work doesn't stop. Decision: D-055.

## What Phase 6 adds

When Empire runs ads, the website can measure them, and only for visitors who agree:

- a consent banner;
- analytics and ad tags (Google and Meta) that load only after the matching consent;
- each enquiry reported to the ad platforms from the server, only when the buyer ticked the optional marketing box.

**Everything ships switched off.**
- A tag runs only once its ID is typed into **CMS → Settings → Tracking**.
- Server-side reports need an access token set as an environment variable.
- Until then the website behaves exactly as at launch: no banner, no tags, nothing sent anywhere.

So Phase 6 can merge before go-live with no effect on the launch.

## Already built in Phase 5 (not repeated)

| Item from ARCHITECTURE §17 | Where it is |
|---|---|
| Campaign landing pages (kind `landing`, own form, never indexed) | Task 5.5a, D-045 |
| WhatsApp click-to-chat with the page in the message, mobile sticky bar | Task 5.2 (`MobileActionBar`, footer) |
| Campaign tags and ad click IDs stored with each lead | Task 5.4 (`AttributionCapture`) |
| Leads by campaign, counts only | `/admin/reports/utm` |
| Tracking IDs in Settings (GTM, GA4, Meta Pixel, Google Ads) | Settings → Tracking (validated; not yet used by the website) |

## Owner's answers (6 Nov 2026)

- **Which ad platforms:** not decided yet. Build for Google (GTM, GA4, Google Ads) and Meta (Pixel, Conversions API). Whichever IDs are filled in are the ones that run.
- **NRI enquiries (foreign mobile numbers):** later. Phase 6 keeps Indian numbers only (`leads/phone.py` TODO stays).
- **WhatsApp lead alerts (WhatsApp Business API):** later. It needs a Meta business account, verification and a cost per message. Email alerts stay.

## Tasks

| Task | Track (D-040) | What | Depends on | Decision | Status |
|---|---|---|---|---|---|
| **6.1** Consent banner | B (developer agent) | The banner, the visitor's choice stored in the browser, and "Cookie settings" in the footer. No tags yet | — | D-056 | Merged 7 Nov (#44), [6.1-consent-banner.md](6.1-consent-banner.md) |
| **6.2** Server-side conversions | A (Claude) | Outbox consumers on `lead.created` for Meta Conversions API and Google Ads, sent only with marketing consent, hashed contact details, off until a token is set | — | D-057 | Merged 7 Nov (#43) |
| **6.3** Tags after consent | A (Claude) | The public site sends the tracking IDs; GTM, GA4, Google Ads and Meta Pixel load only after consent (Google Consent Mode v2 defaults to denied); CSP allows their hosts only when an ID is set; privacy policy cookie section | 6.1 merged | D-058 | **In review** (`feat/p6-3-tags`) |

**Later, when the owner decides:** NRI leads; WhatsApp lead alerts; CRM or webhook export; the daily digest of failed outbox events (`TODO(phase-6)` in `outbox_drain.py`); the list of people in the audit log (`TODO(phase-6)` in `AuditScreen.tsx`).

## Rules for the whole phase

- **Consent first (DPDP Act, 2023).**
  - No tag, pixel or third-party request runs before the visitor chooses.
  - "Accept all" and "Reject all" are equally easy.
  - Nothing is pre-ticked.
  - The choice can be changed at any time from the footer.
- **Server-side reports** go only for leads whose marketing consent is `true`, and carry hashed (SHA-256) contact details only.
- **Wording:** the banner and the cookie section of the privacy policy are drafts marked `[DRAFT]` until the legal reviewer approves them, like the other legal texts (D-017).
- **Performance stays green.**
  - The banner renders after hydration in a fixed position, so it causes no layout shift.
  - The tags load only after consent.
  - The Lighthouse budget (D-049) runs with no IDs set, so it measures the site as launched.

/**
 * The fields of each plain Settings section (board NoirCmsSettings), keyed by settings group and
 * key as the API stores them (`GET /admin/settings`). Sections with their own controls (RERA,
 * lead routing, email and integrations, privacy, consent texts, flags) build on these.
 *
 * Wording and placeholders follow the board; `[brackets]` mark what the owner still has to
 * send (CODE_STYLE §7). Formats are checked by the API (GSTIN, phone numbers per D-034, emails,
 * https links on an allow-list of hosts, tracking IDs); the hints only explain them early.
 */
import type { FieldDef } from "./fieldValues";

export const COMPANY_FIELDS: readonly FieldDef[] = [
  {
    group: "company",
    key: "legal_name",
    label: "Legal name",
    kind: "text",
    maxLength: 120,
    placeholder: "[Company legal name]",
  },
  {
    group: "company",
    key: "brand_name",
    label: "Brand name",
    kind: "text",
    maxLength: 80,
    placeholder: "Empire",
  },
  {
    group: "company",
    key: "gstin",
    label: "GSTIN",
    kind: "id",
    maxLength: 15,
    placeholder: "[GSTIN]",
    hint: "15 characters, as on the GST registration certificate; the last one is a check character. Leave empty until it's confirmed.",
  },
  {
    group: "company",
    key: "tagline",
    label: "Tagline",
    kind: "text",
    maxLength: 120,
    placeholder: "Delivering Happiness",
  },
  {
    group: "company",
    key: "registered_address",
    label: "Registered office address",
    kind: "textarea",
    maxLength: 300,
    wide: true,
    placeholder: "[Registered office address, city, PIN]",
  },
  {
    group: "company",
    key: "corporate_address",
    label: "Corporate office address",
    kind: "textarea",
    maxLength: 300,
    wide: true,
    placeholder: "[Corporate office address, city, PIN]",
    hint: "Shown in the footer and on the Contact page. Site offices are set on each project.",
  },
  {
    group: "social",
    key: "facebook",
    label: "Facebook",
    kind: "url",
    maxLength: 300,
    placeholder: "[Facebook page URL]",
  },
  {
    group: "social",
    key: "instagram",
    label: "Instagram",
    kind: "url",
    maxLength: 300,
    placeholder: "[Instagram profile URL]",
  },
  {
    group: "social",
    key: "youtube",
    label: "YouTube",
    kind: "url",
    maxLength: 300,
    placeholder: "[YouTube channel URL]",
  },
  {
    group: "social",
    key: "linkedin",
    label: "LinkedIn",
    kind: "url",
    maxLength: 300,
    placeholder: "[LinkedIn page URL]",
  },
];

export const CONTACT_FIELDS: readonly FieldDef[] = [
  {
    group: "contacts",
    key: "sales_phone",
    label: "Sales phone",
    kind: "tel",
    maxLength: 20,
    placeholder: "[Sales phone number]",
  },
  {
    group: "contacts",
    key: "whatsapp_number",
    label: "WhatsApp number",
    kind: "tel",
    maxLength: 20,
    placeholder: "[WhatsApp business number]",
    hint: "Used by every WhatsApp button and the mobile bar. A mobile number.",
  },
  {
    group: "contacts",
    key: "customer_care_phone",
    label: "Customer-care phone",
    kind: "tel",
    maxLength: 20,
    placeholder: "[Customer-care number]",
    hint: "For people who already own an Empire home.",
  },
  {
    group: "contacts",
    key: "office_hours",
    label: "Office hours",
    kind: "text",
    maxLength: 120,
    placeholder: "[Days and hours]",
    hint: "Shown next to the phone numbers and the callback promise.",
  },
  {
    group: "contacts",
    key: "sales_email",
    label: "Sales email",
    kind: "email",
    maxLength: 254,
    placeholder: "[sales@empirebuildcon.com]",
  },
  {
    group: "contacts",
    key: "customer_care_email",
    label: "Customer-care email",
    kind: "email",
    maxLength: 254,
    placeholder: "[care@empirebuildcon.com]",
  },
  {
    group: "contacts",
    key: "grievance_officer_name",
    label: "Grievance officer (privacy)",
    kind: "text",
    maxLength: 80,
    placeholder: "[Name, designation]",
    hint: "Named in the privacy notice under India's DPDP law.",
  },
  {
    group: "contacts",
    key: "privacy_email",
    label: "Privacy contact email",
    kind: "email",
    maxLength: 254,
    placeholder: "[privacy@empirebuildcon.com]",
    hint: "Where buyers ask to see, correct or erase their data.",
  },
  {
    group: "contacts",
    key: "whatsapp_message",
    label: "WhatsApp opening message",
    kind: "text",
    maxLength: 300,
    wide: true,
    placeholder: "Hi Empire, I'd like to know more about {page}.",
    hint: "{page} is replaced with the page the visitor is on, so sales knows what they were looking at.",
  },
];

export const TRACKING_FIELDS: readonly FieldDef[] = [
  {
    group: "tracking",
    key: "gtm_id",
    label: "Google Tag Manager container",
    kind: "id",
    maxLength: 20,
    placeholder: "GTM-XXXXXXX",
    hint: "Loads the other tags. Needs analytics or marketing consent.",
  },
  {
    group: "tracking",
    key: "ga4_id",
    label: "Google Analytics 4 measurement ID",
    kind: "id",
    maxLength: 20,
    placeholder: "G-XXXXXXXXXX",
    hint: "Needs analytics consent.",
  },
  {
    group: "tracking",
    key: "meta_pixel_id",
    label: "Meta Pixel ID",
    kind: "id",
    maxLength: 20,
    placeholder: "15–16 digit pixel ID",
    hint: "Needs marketing consent.",
  },
  {
    group: "tracking",
    key: "google_ads_id",
    label: "Google Ads conversion ID",
    kind: "id",
    maxLength: 20,
    placeholder: "AW-XXXXXXXXX",
    hint: "Needs marketing consent.",
  },
];

export const SEO_FIELDS: readonly FieldDef[] = [
  {
    group: "seo_defaults",
    key: "default_title",
    label: "Default page title",
    kind: "text",
    maxLength: 70,
    placeholder: "Empire — Delivering Happiness",
    hint: "Used when a page has no title of its own.",
  },
  {
    group: "seo_defaults",
    key: "title_suffix",
    label: "Title ending",
    kind: "text",
    maxLength: 40,
    keepSpaces: true,
    placeholder: " · Empire",
    hint: "Added straight after every page's title in search results. Start it with a space, so titles read “Aurum Heights · Empire”; spaces here are kept as typed.",
  },
  {
    group: "seo_defaults",
    key: "default_description",
    label: "Default description",
    kind: "textarea",
    maxLength: 170,
    wide: true,
    placeholder:
      "[One or two sentences about Empire's homes in Uttar Pradesh, about 150 characters]",
    hint: "Used when a page has no description of its own. About 150 characters reads well in search results.",
  },
];

export const EMAIL_FIELDS: readonly FieldDef[] = [
  {
    group: "email",
    key: "sender_name",
    label: "Sender name",
    kind: "text",
    maxLength: 60,
    placeholder: "Empire",
    hint: "The name people see on lead alerts and password emails. Letters, digits, spaces and . - & ' only.",
  },
  {
    group: "email",
    key: "reply_to",
    label: "Reply-to address",
    kind: "email",
    maxLength: 254,
    placeholder: "[sales@empirebuildcon.com]",
    hint: "Where replies go. The sending address itself is set in the server environment.",
  },
];

export const RERA_FIELDS: readonly FieldDef[] = [
  {
    group: "regulator",
    key: "promoter_registration_number",
    label: "Promoter registration number",
    kind: "id",
    maxLength: 40,
    placeholder: "[Promoter registration number, if any]",
    hint: "Only if Empire holds one; leave empty otherwise. Letters, digits, / and - as UP-RERA shows it.",
  },
];

export const PRIVACY_FIELDS: readonly FieldDef[] = [
  {
    group: "privacy",
    key: "lead_retention_years",
    label: "Keep leads for (years)",
    kind: "number",
    min: 1,
    max: 10,
    hint: "1 to 10 years. Leads with no real activity for this long have their personal details removed by the daily clean-up; the reference and counts stay.",
  },
];

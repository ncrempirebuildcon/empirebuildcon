/**
 * The Settings screen's sections (board NoirCmsSettings's left list, plus Privacy and Consent
 * texts from the Phase 4 part 5 spec), in order: what each is called, the hint under its name,
 * the sentence under its heading, the settings groups it saves, and the permission its Save
 * needs (shown as "Needs …").
 *
 * For sections that save settings groups, who may edit comes from the API's own answer
 * (`SettingsOverview.groups[].can_edit` and `.permission`), so the screen can't drift from the
 * rules it enforces. Consent texts and flags have their own permissions.
 *
 * SECURITY: this only decides what the screen offers. The API checks the same rule on every
 * save (ARCHITECTURE §11), including the super-admin rule for the retention period.
 */
import type { GroupKey, SettingsState } from "./useSettings";

export const SETTINGS_SECTIONS = [
  {
    id: "company",
    groups: ["company", "social"] as readonly GroupKey[],
    label: "Company",
    hint: "Name, GSTIN, offices",
    intro: "Legal details shown in the footer, the Contact page and the legal pages.",
    permission: "settings.write",
  },
  {
    id: "rera",
    groups: ["regulator"] as readonly GroupKey[],
    label: "RERA",
    hint: "Authority, QR rule",
    intro:
      "Which RERA authority Empire's projects are registered with, and how RERA details show on the site.",
    permission: "settings.write",
  },
  {
    id: "contacts",
    groups: ["contacts"] as readonly GroupKey[],
    label: "Contacts",
    hint: "Phones, WhatsApp, emails",
    intro: "Numbers and addresses used by every Call, WhatsApp and email button.",
    permission: "settings.write",
  },
  {
    id: "routing",
    groups: ["lead_routing"] as readonly GroupKey[],
    label: "Lead routing",
    hint: "Inbox, round robin",
    intro: "Where new leads go and who gets them.",
    permission: "settings.write",
  },
  {
    id: "tracking",
    groups: ["tracking"] as readonly GroupKey[],
    label: "Tracking",
    hint: "GTM, GA4, Pixel, Ads",
    intro: "Analytics and ad tags. They load only with the visitor's consent.",
    permission: "marketing.tracking",
  },
  {
    id: "integrations",
    groups: ["email"] as readonly GroupKey[],
    label: "Email and integrations",
    hint: "Email, CRM, webhooks",
    intro:
      "Services the CMS sends data to, and how emails are signed. Keys and secrets live in the server environment.",
    permission: "settings.write",
  },
  {
    id: "seo",
    groups: ["seo_defaults"] as readonly GroupKey[],
    label: "SEO defaults",
    hint: "Titles, descriptions",
    intro: "Defaults for search results and link previews when a page has none of its own.",
    permission: "seo.manage",
  },
  {
    id: "privacy",
    groups: ["privacy"] as readonly GroupKey[],
    label: "Privacy",
    hint: "How long leads are kept",
    intro: "How long enquiries are kept before their personal details are removed.",
    permission: "settings.write",
  },
  {
    id: "consent",
    groups: [] as readonly GroupKey[],
    label: "Consent texts",
    hint: "Form wording, versions",
    intro:
      "The wording visitors agree to on the forms. Versions are never edited after publishing; publish a new one instead.",
    permission: "legal.publish",
  },
  {
    id: "flags",
    groups: [] as readonly GroupKey[],
    label: "Feature flags",
    hint: "Switch features on or off",
    intro: "Features that are built but switched off, or reserved for later.",
    permission: "flags.manage",
  },
] as const;

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]["id"];

export function isSettingsSection(value: string | null): value is SettingsSectionId {
  return SETTINGS_SECTIONS.some((section) => section.id === value);
}

/** What every section body receives. */
export interface SectionProps {
  settings: SettingsState;
  canSave: boolean;
  onDirtyChange: (dirty: boolean) => void;
}

/** What the section's Save needs, for "Needs …" and the read-only note. */
export function sectionNeeds(id: SettingsSectionId, settings: SettingsState): string {
  const section = SETTINGS_SECTIONS.find((s) => s.id === id);
  if (!section) return "";
  const metas = section.groups.map((key) => settings.meta[key]).filter((m) => m !== undefined);
  if (metas.length === 0) return section.permission;
  const permissions = [...new Set(metas.map((m) => m.permission))].join(", ");
  return metas.some((m) => m.super_admin_only) ? `${permissions} · super-admin` : permissions;
}

/** "You can view these settings. Changing them needs settings.write." */
export function readOnlyReason(id: SettingsSectionId, settings: SettingsState): string {
  const needs = sectionNeeds(id, settings).replace(" · super-admin", " and the super-admin role");
  return `You can view these settings. Changing them needs ${needs}.`;
}

/**
 * Whether the signed-in person can save a section: every group it saves must be editable for
 * them (the API's `can_edit`); consent texts need legal.publish, flags flags.manage.
 * COMPLIANCE: the retention period (Privacy) needs a super-admin; the API says so in `can_edit`.
 */
export function canSaveSection(
  id: SettingsSectionId,
  settings: SettingsState,
  can: (permission: string) => boolean,
): boolean {
  const section = SETTINGS_SECTIONS.find((s) => s.id === id);
  if (!section) return false;
  if (section.groups.length === 0) return can(section.permission);
  return section.groups.every((key) => settings.meta[key]?.can_edit === true);
}

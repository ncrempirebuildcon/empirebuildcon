// Settings rules a browser test can't reach without another role's sign-in (Phase 4 part 5):
// who may save each section (from the API's own group metadata; the retention period needs a
// super-admin), and the lead-routing draft, which must never save an untouched rotation, so an
// empty list keeps meaning "every active sales user".
import { describe, expect, it } from "vitest";
import { canSaveSection, readOnlyReason, sectionNeeds } from "@/app/admin/settings/sections";
import {
  errorsByPerson,
  removeFromRotation,
  routingDraft,
  routingPatch,
  setInRotation,
  unusableReason,
} from "@/app/admin/settings/routing";
import { failedEmailsText } from "@/app/admin/settings/integrations";
import { PRIVACY_FIELDS, SEO_FIELDS } from "@/app/admin/settings/fields";
import { draftOf, patchesOf } from "@/app/admin/settings/fieldValues";
import type { GroupMeta, SettingsState } from "@/app/admin/settings/useSettings";

function meta(key: GroupMeta["key"], permission: string, canEdit: boolean, superAdminOnly = false) {
  return {
    key,
    label: key,
    permission,
    super_admin_only: superAdminOnly,
    can_edit: canEdit,
    updated_at: null,
    updated_by: null,
  } satisfies GroupMeta;
}

function settings(metas: GroupMeta[]): SettingsState {
  return {
    groups: {},
    meta: Object.fromEntries(metas.map((m) => [m.key, m])),
    reload: () => undefined,
    save: async () => undefined,
  };
}

// As the API answers an admin: everything but the retention period (super-admin only).
const asAdmin = settings([
  meta("company", "settings.write", true),
  meta("social", "settings.write", true),
  meta("tracking", "marketing.tracking", true),
  meta("privacy", "settings.write", false, true),
]);
// As the API answers marketing: tracking only (and SEO), the rest read-only.
const asMarketing = settings([
  meta("company", "settings.write", false),
  meta("social", "settings.write", false),
  meta("tracking", "marketing.tracking", true),
  meta("privacy", "settings.write", false, true),
]);

describe("who may save a section", () => {
  it("follows the API's can_edit for every group the section saves", () => {
    const yes = () => true;
    expect(canSaveSection("company", asAdmin, yes)).toBe(true);
    expect(canSaveSection("company", asMarketing, yes)).toBe(false);
    expect(canSaveSection("tracking", asMarketing, yes)).toBe(true);
  });

  it("keeps the retention period for the super-admin (COMPLIANCE)", () => {
    expect(canSaveSection("privacy", asAdmin, () => true)).toBe(false);
    expect(sectionNeeds("privacy", asAdmin)).toBe("settings.write · super-admin");
    expect(readOnlyReason("privacy", asAdmin)).toBe(
      "You can view these settings. Changing them needs settings.write and the super-admin role.",
    );
  });

  it("uses the permission itself for consent texts and flags", () => {
    const legalOnly = (p: string) => p === "legal.publish";
    expect(canSaveSection("consent", asAdmin, legalOnly)).toBe(true);
    expect(canSaveSection("flags", asAdmin, legalOnly)).toBe(false);
    expect(sectionNeeds("flags", asAdmin)).toBe("flags.manage");
  });
});

const ana = "11111111-1111-4111-8111-111111111111";
const bo = "22222222-2222-4222-8222-222222222222";
const cy = "33333333-3333-4333-8333-333333333333";

describe("lead routing draft", () => {
  it("shows the API's effective list when none is stored, and saves nothing untouched", () => {
    const saved = routingDraft({ mode: "round_robin", round_robin_user_ids: [] }, [ana, bo]);
    expect(saved.list).toEqual([ana, bo]);
    expect(routingPatch(saved, saved)).toEqual({});
  });

  it("sends the order when it changes, and empty text as null", () => {
    const saved = routingDraft(
      { mode: "single", inbox_email: "sales@example.com", round_robin_user_ids: [ana, bo] },
      [],
    );
    const draft = { ...saved, list: [bo, ana], inbox_email: "  " };
    expect(routingPatch(draft, saved)).toEqual({
      inbox_email: null,
      round_robin_user_ids: [bo, ana],
    });
  });

  it("sends the list with any pause, so every paused id is in the stored list", () => {
    const saved = routingDraft({ round_robin_user_ids: [] }, [ana, bo]);
    const draft = setInRotation(saved, bo, false);
    expect(routingPatch(draft, saved)).toEqual({
      round_robin_user_ids: [ana, bo],
      round_robin_paused_user_ids: [bo],
    });
  });

  it("adds a new person to the end, and switching back on un-pauses", () => {
    const saved = routingDraft(
      { round_robin_user_ids: [ana], round_robin_paused_user_ids: [ana] },
      [],
    );
    const added = setInRotation(saved, cy, true);
    expect(added.list).toEqual([ana, cy]);
    const back = setInRotation(added, ana, true);
    expect(back.paused).toEqual([]);
  });

  it("reads unknown modes as single", () => {
    expect(routingDraft({ mode: "nonsense" }, []).mode).toBe("single");
    expect(routingDraft({ mode: "manual" }, []).mode).toBe("manual");
  });
});

describe("failed emails", () => {
  it("says how many failed, in words, or nothing", () => {
    expect(failedEmailsText(0)).toBeNull();
    expect(failedEmailsText(1)).toBe("1 email couldn't be sent in the last 7 days.");
    expect(failedEmailsText(3)).toBe("3 emails couldn't be sent in the last 7 days.");
  });
});

describe("settings form values (review L3)", () => {
  const suffix = SEO_FIELDS.find((field) => field.key === "title_suffix");
  const title = SEO_FIELDS.find((field) => field.key === "default_title");

  it("keeps the leading space of the title ending", () => {
    expect(suffix?.keepSpaces).toBe(true);
    const fields = [suffix, title].filter((f) => f !== undefined);
    const saved = draftOf(fields, {
      seo_defaults: { title_suffix: " · Empire", default_title: "A" },
    });
    const draft = {
      ...saved,
      "seo_defaults.title_suffix": " · Empire Buildcon",
      "seo_defaults.default_title": "  Empire homes  ",
    };
    expect(patchesOf(fields, draft, saved)).toEqual({
      seo_defaults: { title_suffix: " · Empire Buildcon", default_title: "Empire homes" },
    });
  });

  it("still sends a blank title ending as null", () => {
    const fields = [suffix].filter((f) => f !== undefined);
    const saved = draftOf(fields, { seo_defaults: { title_suffix: " · Empire" } });
    expect(patchesOf(fields, { "seo_defaults.title_suffix": "   " }, saved)).toEqual({
      seo_defaults: { title_suffix: null },
    });
  });

  it("sends numbers as numbers and leaves unchanged fields out", () => {
    const saved = draftOf(PRIVACY_FIELDS, { privacy: { lead_retention_years: 3 } });
    expect(saved).toEqual({ "privacy.lead_retention_years": "3" });
    expect(patchesOf(PRIVACY_FIELDS, saved, saved)).toEqual({});
    expect(patchesOf(PRIVACY_FIELDS, { "privacy.lead_retention_years": "4" }, saved)).toEqual({
      privacy: { lead_retention_years: 4 },
    });
  });
});

describe("people who left the rotation (review M3)", () => {
  it("can always be removed, from the list and from the paused ones", () => {
    const saved = routingDraft(
      { round_robin_user_ids: [ana, bo, cy], round_robin_paused_user_ids: [bo] },
      [],
    );
    const draft = removeFromRotation(saved, bo);
    expect(draft.list).toEqual([ana, cy]);
    expect(draft.paused).toEqual([]);
    expect(routingPatch(draft, saved)).toEqual({
      round_robin_user_ids: [ana, cy],
      round_robin_paused_user_ids: [],
    });
  });

  it("are shown with the reason routing skips them", () => {
    expect(unusableReason(undefined)).toBeNull();
    expect(unusableReason({ can_own: true, role: "sales" })).toBeNull();
    expect(unusableReason({ can_own: false, role: "marketing" })).toBe(
      "Skipped: Marketing can't own leads.",
    );
    expect(unusableReason({ can_own: false, role: "sales" })).toBe(
      "Skipped: deactivated, or hasn't set a password yet.",
    );
  });

  it("get the API's message next to them", () => {
    expect(
      errorsByPerson(
        { "round_robin_user_ids.1": "Choose someone active.", inbox_email: "Bad email." },
        [ana, bo],
      ),
    ).toEqual({ [bo]: "Choose someone active." });
  });
});

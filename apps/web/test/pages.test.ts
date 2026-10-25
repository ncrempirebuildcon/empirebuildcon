// Who may change a page (review H2, D-017): a legal page that is live OR scheduled to go live
// changes only with `legal.publish`, because the schedule tick publishes its text unchecked.
// The page editor uses these to lock its fields and blocks; the API enforces the same rule.
import { describe, expect, it } from "vitest";
import { canEditPage, isGuardedLegal, readOnlyReason } from "@/lib/content/pages";

const contentEditor = (permission: string) =>
  ["content.read", "content.write", "content.publish"].includes(permission);
const admin = (permission: string) => contentEditor(permission) || permission === "legal.publish";
const viewer = (permission: string) => permission === "content.read";

const tomorrow = "2026-10-26T04:30:00Z";
const draftLegal = { kind: "legal", publish_state: "draft", publish_at: null } as const;
const scheduledLegal = { ...draftLegal, publish_at: tomorrow } as const;
const liveLegal = { ...draftLegal, publish_state: "published" } as const;
const scheduledStandard = { ...scheduledLegal, kind: "standard" } as const;

describe("legal pages that are live or scheduled", () => {
  it("counts a scheduled draft legal page as guarded, like a live one", () => {
    expect(isGuardedLegal(scheduledLegal)).toBe(true);
    expect(isGuardedLegal(liveLegal)).toBe(true);
    expect(isGuardedLegal(draftLegal)).toBe(false);
    expect(isGuardedLegal(scheduledStandard)).toBe(false);
  });

  it("is read-only for a content editor without legal.publish once it is scheduled", () => {
    expect(canEditPage(scheduledLegal, contentEditor)).toBe(false);
    expect(readOnlyReason(scheduledLegal, contentEditor)).toMatch(
      /^This legal page is scheduled to go live: changing it needs the legal\.publish permission/,
    );
  });

  it("stays editable for a content editor while it is an unscheduled draft", () => {
    expect(canEditPage(draftLegal, contentEditor)).toBe(true);
    expect(readOnlyReason(draftLegal, contentEditor)).toBeNull();
  });

  it("says a live legal page needs legal.publish", () => {
    expect(readOnlyReason(liveLegal, contentEditor)).toBe(
      "This legal page is live: changing it needs the legal.publish permission.",
    );
  });

  it("lets legal.publish change it, live or scheduled", () => {
    expect(canEditPage(scheduledLegal, admin)).toBe(true);
    expect(canEditPage(liveLegal, admin)).toBe(true);
  });

  it("doesn't touch other kinds of page", () => {
    expect(canEditPage(scheduledStandard, contentEditor)).toBe(true);
  });

  it("is read-only without content.write, whatever the page", () => {
    expect(canEditPage(draftLegal, viewer)).toBe(false);
    expect(readOnlyReason(scheduledStandard, viewer)).toBe(
      "You can view this page. Editing needs the content.write permission.",
    );
  });
});

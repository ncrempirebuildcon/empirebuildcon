// Reading audit entries (board NoirCmsAudit): the action chips, plain words for an action, and
// the before/after lines of `changes` as apps/api platform/audit.py writes them.
import { describe, expect, it } from "vitest";
import {
  AUDIT_ACTION_FILTERS,
  actionQuery,
  actionWords,
  auditKind,
  auditLines,
  auditValue,
} from "@/lib/audit";

describe("which chip an action belongs to", () => {
  it.each([
    ["auth.login", "login"],
    ["auth.login_failed", "login"],
    ["user.locked", "login"],
    ["project.published", "publish"],
    ["page.unpublished", "publish"],
    ["page.scheduled_publish_cancelled", "publish"],
    ["project.archived", "publish"],
    ["lead.exported", "export"],
    ["lead.erased", "erasure"],
    ["user.created", "permission"],
    ["user.updated", "permission"],
    ["user.two_factor_reset", "permission"],
    ["flag.changed", "permission"],
    ["settings.updated", "update"],
    ["offer.updated", "update"],
    ["media_link.reordered", "update"],
    ["lead.note_added", "update"],
    ["something.new", "other"],
  ])("%s → %s", (action, kind) => {
    expect(auditKind(action)).toBe(kind);
  });
});

describe("plain words for an action", () => {
  it("uses its own words for the common ones and a pattern for the rest", () => {
    expect(actionWords("auth.login")).toBe("Signed in");
    expect(actionWords("user.created")).toBe("User invited");
    expect(actionWords("project.published")).toBe("Project published");
    expect(actionWords("media_link.updated")).toBe("Media link changed");
    expect(actionWords("lead.exported")).toBe("Lead exported");
    expect(actionWords("odd")).toBe("Odd");
  });
});

describe("before and after lines", () => {
  it("splits [before, after] pairs and keeps other facts as information", () => {
    expect(
      auditLines({
        status: ["draft", "published"],
        is_active: [true, false],
        locked_until: ["2026-10-20T16:28:00Z", null],
        rows: 48,
        filters: { project: "aurum" },
      }),
    ).toEqual({
      before: ["status: draft", "is active: yes", "locked until: 2026-10-20T16:28:00Z"],
      after: ["status: published", "is active: no", "locked until: (none)"],
      info: ["Rows: 48", 'Filters: {"project":"aurum"}'],
    });
  });

  it("is empty for an entry without changes", () => {
    expect(auditLines({})).toEqual({ before: [], after: [], info: [] });
  });

  it("shortens a very long value", () => {
    const value = auditValue(Array.from({ length: 80 }, (_, i) => `id-${i}`));
    expect(value.length).toBe(200);
    expect(value.endsWith("…")).toBe(true);
  });
});

describe("action filters", () => {
  it("are queries the API can answer on the server", () => {
    expect(actionQuery("")).toEqual({});
    expect(actionQuery("signins")).toEqual({ action_prefix: "auth." });
    expect(actionQuery("exports")).toEqual({ action: "lead.exported" });
    expect(actionQuery("erasures")).toEqual({ action: "lead.erased" });
  });

  it("each filter's entries land in the matching chip where the chip exists", () => {
    expect(auditKind("auth.login")).toBe("login");
    expect(auditKind(AUDIT_ACTION_FILTERS.exports.query.action)).toBe("export");
    expect(auditKind(AUDIT_ACTION_FILTERS.erasures.query.action)).toBe("erasure");
  });
});

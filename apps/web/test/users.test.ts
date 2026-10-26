// Users & roles (board NoirCmsUsers): the permission table's groups, the avatar initials and
// the role picker's counts. Which role has which permission comes from the API only.
import { describe, expect, it } from "vitest";
import {
  accountStatus,
  groupPermissions,
  initials,
  permissionGroup,
  userCountText,
} from "@/lib/users";

describe("permission groups", () => {
  it("puts each permission under the board's heading", () => {
    expect(permissionGroup("dashboard.view")).toBe("Dashboard & projects");
    expect(permissionGroup("projects.publish")).toBe("Dashboard & projects");
    expect(permissionGroup("media.manage")).toBe("Media");
    expect(permissionGroup("site_visits.manage")).toBe("Leads & site visits");
    expect(permissionGroup("legal.publish")).toBe("Content & SEO");
    expect(permissionGroup("marketing.tracking")).toBe("Settings & system");
    expect(permissionGroup("users.manage")).toBe("Settings & system");
    expect(permissionGroup("webhooks.manage")).toBe("Other");
  });

  it("uses the API's groups, in the order they come, with the API's row order", () => {
    const groups = groupPermissions([
      { key: "dashboard.view", group: "Dashboard & projects" },
      { key: "projects.read", group: "Dashboard & projects" },
      { key: "users.manage", group: "Settings & system" },
      { key: "audit.read", group: "Settings & system" },
    ]);
    expect(groups.map((g) => g.name)).toEqual(["Dashboard & projects", "Settings & system"]);
    expect(groups[1]?.rows.map((r) => r.key)).toEqual(["users.manage", "audit.read"]);
  });

  it("falls back to the prefix when a row has no group", () => {
    const groups = groupPermissions([{ key: "media.upload" }, { key: "leads.read", group: "" }]);
    expect(groups.map((g) => g.name)).toEqual(["Media", "Leads & site visits"]);
  });
});

describe("initials and counts", () => {
  it("makes at most two letters", () => {
    expect(initials("Sales One")).toBe("SO");
    expect(initials("Mary Ann Smith")).toBe("MA");
    expect(initials("admin")).toBe("AD");
    expect(initials("  ")).toBe("?");
  });

  it("says how many users a role has in words", () => {
    expect(userCountText(0)).toBe("No users");
    expect(userCountText(1)).toBe("1 user");
    expect(userCountText(4)).toBe("4 users");
  });
});

describe("account status", () => {
  const now = Date.parse("2026-10-25T12:00:00Z");
  const base = { is_active: true, locked_until: null, last_login_at: "2026-10-24T10:00:00Z" };

  it("prefers the API's own status", () => {
    expect(accountStatus({ ...base, status: "invited" }, now)).toBe("invited");
    expect(accountStatus({ ...base, status: "nonsense" }, now)).toBe("active");
  });

  it("works it out when the API sends no status", () => {
    expect(accountStatus(base, now)).toBe("active");
    expect(accountStatus({ ...base, is_active: false }, now)).toBe("deactivated");
    expect(accountStatus({ ...base, locked_until: "2026-10-25T12:10:00Z" }, now)).toBe("locked");
    expect(accountStatus({ ...base, locked_until: "2026-10-25T11:50:00Z" }, now)).toBe("active");
    expect(accountStatus({ ...base, last_login_at: null }, now)).toBe("invited");
  });
});

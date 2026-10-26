// Setup and reset links (SECURITY.md §1): the token is read once, only in a sane shape, and the
// address the page puts back with history.replaceState no longer carries it. The password
// length rule matches the API's wording and counts characters the way Python does.
import { describe, expect, it } from "vitest";
import {
  DONE_MESSAGES,
  addressWithoutToken,
  doneKind,
  hasToken,
  passwordProblem,
  tokenFromLocation,
  tokenFromSearch,
} from "@/lib/auth/links";

// WHY built at runtime: a literal random-looking string trips the secret scan (SECURITY.md §7).
const token = `fake_${"Ab9-".repeat(10)}`;

describe("reading the token from a link", () => {
  it("reads a URL-safe token", () => {
    expect(tokenFromSearch(`?token=${token}`)).toBe(token);
    expect(tokenFromSearch(`?a=1&token=${token}`)).toBe(token);
  });

  it.each([
    ["no token", "?a=1"],
    ["an empty token", "?token="],
    ["too short", "?token=abc"],
    ["too long", `?token=${"a".repeat(201)}`],
    ["a character outside URL-safe base64", "?token=abcdefghijklmnop%2Fq"],
    ["markup", "?token=%3Cscript%3Ealert(1)%3C%2Fscript%3E"],
  ])("refuses %s", (_label, search) => {
    expect(tokenFromSearch(search)).toBeNull();
  });
});

describe("reading the token from the fragment (review L10)", () => {
  it("prefers the fragment, which never reaches a server", () => {
    expect(tokenFromLocation(`#token=${token}`, "")).toBe(token);
    expect(tokenFromLocation(`#token=${token}`, "?token=abcdefghijklmnopqrstuvwx")).toBe(token);
  });

  it("still reads links sent with ?token=", () => {
    expect(tokenFromLocation("", `?token=${token}`)).toBe(token);
    expect(tokenFromLocation("#other=1", `?token=${token}`)).toBe(token);
  });

  it("refuses a malformed token in either place", () => {
    expect(tokenFromLocation("#token=short", "")).toBeNull();
    expect(tokenFromLocation("", "")).toBeNull();
  });

  it("knows when the address still carries a token", () => {
    expect(hasToken("", `#token=${token}`)).toBe(true);
    expect(hasToken(`?token=${token}`, "")).toBe(true);
    expect(hasToken("?a=1", "#top")).toBe(false);
  });
});

describe("removing the token from the address bar", () => {
  it("drops a token in the fragment, keeping anything else", () => {
    expect(addressWithoutToken("/admin/setup", "", `#token=${token}`)).toBe("/admin/setup");
    expect(addressWithoutToken("/admin/reset", "?x=1", `#token=${token}&y=2`)).toBe(
      "/admin/reset?x=1#y=2",
    );
    expect(addressWithoutToken("/admin/reset", `?token=${token}`, `#token=${token}`)).toBe(
      "/admin/reset",
    );
  });

  it("keeps the path, other parameters and the fragment, and drops only the token", () => {
    expect(addressWithoutToken("/admin/setup", `?token=${token}`)).toBe("/admin/setup");
    expect(addressWithoutToken("/admin/reset", `?x=1&token=${token}&y=2`, "#top")).toBe(
      "/admin/reset?x=1&y=2#top",
    );
  });

  it("never leaves the token anywhere in the new address", () => {
    const address = addressWithoutToken("/admin/reset", `?token=${token}&token=${token}`);
    expect(address).not.toContain(token);
    expect(address).not.toContain("token");
  });
});

describe("the new password's length", () => {
  it("uses the API's words", () => {
    expect(passwordProblem("short")).toBe("Use at least 12 characters.");
    expect(passwordProblem("a".repeat(201))).toBe("Use at most 200 characters.");
    expect(passwordProblem("a quiet morning by the river")).toBeNull();
  });

  it("counts characters, not UTF-16 units (like Python's len)", () => {
    // 11 emoji are 22 UTF-16 units but 11 characters: still too short.
    expect(passwordProblem("🙂".repeat(11))).toBe("Use at least 12 characters.");
    expect(passwordProblem("🙂".repeat(12))).toBeNull();
    expect(passwordProblem("घरकीचाबीमिलगई")).toBeNull();
  });
});

describe("the message after a link was used", () => {
  it("knows setup and reset, and ignores anything else", () => {
    expect(doneKind("setup")).toBe("setup");
    expect(doneKind("reset")).toBe("reset");
    expect(doneKind("<b>hi</b>")).toBeNull();
    expect(doneKind(["setup"])).toBeNull();
    expect(doneKind(undefined)).toBeNull();
    expect(DONE_MESSAGES.reset).toMatch(/signed out everywhere/);
  });
});

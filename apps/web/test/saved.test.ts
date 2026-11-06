// @vitest-environment jsdom
/**
 * Unit tests for saved homes storage (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Verifies:
 * - add items
 * - remove items
 * - the 50-item cap
 * - newest first order
 * - duplicates collapse to one
 * - rubbish in storage discarded safely
 * - strict path validation and kind matching (prevents protocol-relative '//evil' or malformed paths)
 * - versioned payload `{ v: 1, items }` with v0 array backwards compatibility
 * - storage throwing handled gracefully without crashing
 * - window.localStorage getter throwing SecurityError handled gracefully (Must 2)
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import React from "react";
import { act, fireEvent, render } from "@testing-library/react";
import { SaveButton } from "../src/components/tools/SaveButton";
import {
  addSavedItem,
  getSavedHomesSnapshot,
  getSavedItems,
  isItemSaved,
  isStorageAvailable,
  isValidSavedItem,
  MAX_SAVED_ITEMS,
  removeSavedItem,
  safeLocalStorage,
  SAVED_HOMES_STORAGE_KEY,
} from "../src/lib/tools/saved";

class MockStorage implements Storage {
  private store: Map<string, string> = new Map();
  public shouldThrow = false;

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    if (this.shouldThrow) throw new Error("Storage quota exceeded or disabled");
    this.store.clear();
  }

  getItem(key: string): string | null {
    if (this.shouldThrow) throw new Error("Storage quota exceeded or disabled");
    return this.store.get(key) ?? null;
  }

  key(index: number): string | null {
    if (this.shouldThrow) throw new Error("Storage quota exceeded or disabled");
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    if (this.shouldThrow) throw new Error("Storage quota exceeded or disabled");
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    if (this.shouldThrow) throw new Error("Storage quota exceeded or disabled");
    this.store.set(key, value);
  }
}

describe("Saved homes storage (Task 5.7b)", () => {
  let mockStorage: MockStorage;

  beforeEach(() => {
    mockStorage = new MockStorage();
  });

  afterEach(() => {
    // Restore window.localStorage if modified in any test
    delete (window as unknown as Record<string, unknown>).localStorage;
  });

  it("adds items to storage and retrieves them", () => {
    const item1 = {
      kind: "project" as const,
      path: "/projects/empire-heights",
      name: "Empire Heights",
    };
    const res = addSavedItem(item1, mockStorage);
    expect(res.success).toBe(true);
    expect(res.items).toHaveLength(1);
    expect(res.items[0]!.name).toBe("Empire Heights");
    expect(isItemSaved("/projects/empire-heights", mockStorage)).toBe(true);
    expect(isItemSaved("/projects/other-project", mockStorage)).toBe(false);

    const retrieved = getSavedItems(mockStorage);
    expect(retrieved).toHaveLength(1);
    expect(retrieved[0]!.path).toBe("/projects/empire-heights");
  });

  it("removes items by path", () => {
    addSavedItem({ kind: "project", path: "/projects/p1", name: "P1" }, mockStorage);
    addSavedItem({ kind: "property", path: "/projects/p1/3-bhk", name: "3 BHK" }, mockStorage);
    expect(getSavedItems(mockStorage)).toHaveLength(2);

    const res = removeSavedItem("/projects/p1", mockStorage);
    expect(res.success).toBe(true);
    expect(res.items).toHaveLength(1);
    expect(res.items[0]!.path).toBe("/projects/p1/3-bhk");
    expect(isItemSaved("/projects/p1", mockStorage)).toBe(false);
  });

  it("orders items newest first", () => {
    addSavedItem({ kind: "project", path: "/projects/first", name: "First" }, mockStorage);
    addSavedItem({ kind: "project", path: "/projects/second", name: "Second" }, mockStorage);
    addSavedItem(
      { kind: "property", path: "/projects/third/3-bhk", name: "Third 3 BHK" },
      mockStorage,
    );

    const items = getSavedItems(mockStorage);
    expect(items.map((i) => i.name)).toEqual(["Third 3 BHK", "Second", "First"]);
  });

  it("collapses duplicates to one and moves to the top", () => {
    addSavedItem({ kind: "project", path: "/projects/first", name: "First" }, mockStorage);
    addSavedItem({ kind: "project", path: "/projects/second", name: "Second" }, mockStorage);
    expect(getSavedItems(mockStorage)).toHaveLength(2);

    // Re-saving "First" should update it to the top without increasing count
    const res = addSavedItem(
      { kind: "project", path: "/projects/first", name: "First Renamed" },
      mockStorage,
    );
    expect(res.items).toHaveLength(2);
    expect(res.items[0]!.path).toBe("/projects/first");
    expect(res.items[0]!.name).toBe("First Renamed");
    expect(res.items[1]!.path).toBe("/projects/second");
  });

  it("enforces the 50-item cap", () => {
    for (let i = 1; i <= 60; i++) {
      addSavedItem(
        { kind: "project", path: `/projects/p-${i}`, name: `Project ${i}` },
        mockStorage,
      );
    }

    const items = getSavedItems(mockStorage);
    expect(items).toHaveLength(MAX_SAVED_ITEMS);
    expect(items[0]!.name).toBe("Project 60");
    expect(items[MAX_SAVED_ITEMS - 1]!.name).toBe("Project 11");
    expect(isItemSaved("/projects/p-1", mockStorage)).toBe(false);
  });

  it("supports both v1 { v: 1, items } schema and v0 bare array payload", () => {
    // v0 bare array in storage
    const v0List = [
      {
        kind: "project",
        path: "/projects/legacy-proj",
        name: "Legacy Proj",
        savedAt: new Date().toISOString(),
      },
    ];
    mockStorage.setItem(SAVED_HOMES_STORAGE_KEY, JSON.stringify(v0List));

    const retrievedV0 = getSavedItems(mockStorage);
    expect(retrievedV0).toHaveLength(1);
    expect(retrievedV0[0]!.path).toBe("/projects/legacy-proj");

    // Saving an item upgrades storage to v1 schema
    addSavedItem({ kind: "property", path: "/projects/p/2-bhk", name: "2 BHK" }, mockStorage);
    const rawStored = mockStorage.getItem(SAVED_HOMES_STORAGE_KEY);
    expect(rawStored).toContain('"v":1');
    const parsed = JSON.parse(rawStored!);
    expect(parsed.v).toBe(1);
    expect(parsed.items).toHaveLength(2);
  });

  it("safely discards rubbish, tampered paths, and malformed entries in storage", () => {
    const rubbish = [
      null,
      123,
      "plain text string",
      {},
      {
        kind: "unknown",
        path: "/projects/p",
        name: "Invalid Kind",
        savedAt: new Date().toISOString(),
      },
      {
        kind: "project",
        path: "no-leading-slash",
        name: "No Slash",
        savedAt: new Date().toISOString(),
      },
      // Protocol-relative injection attempt (tampered storage)
      {
        kind: "project",
        path: "//evil.example/projects/p",
        name: "Evil Phish",
        savedAt: new Date().toISOString(),
      },
      // Kind mismatch (project with 2 slugs)
      {
        kind: "project",
        path: "/projects/p/extra-slug",
        name: "Mismatched",
        savedAt: new Date().toISOString(),
      },
      // Kind mismatch (property with only 1 slug)
      {
        kind: "property",
        path: "/projects/single-slug",
        name: "Mismatched Property",
        savedAt: new Date().toISOString(),
      },
      { kind: "project", path: "/projects/valid", name: "   ", savedAt: new Date().toISOString() },
      { kind: "project", path: "/projects/valid", name: "Valid Name", savedAt: "invalid-date" },
      {
        kind: "property",
        path: "/projects/p/3-bhk",
        name: "Valid 3 BHK",
        savedAt: new Date().toISOString(),
      },
    ];
    mockStorage.setItem(SAVED_HOMES_STORAGE_KEY, JSON.stringify(rubbish));

    const items = getSavedItems(mockStorage);
    expect(items).toHaveLength(1);
    expect(items[0]!.name).toBe("Valid 3 BHK");

    // Invalid JSON completely
    mockStorage.setItem(SAVED_HOMES_STORAGE_KEY, "not json at all {[]");
    expect(getSavedItems(mockStorage)).toEqual([]);
  });

  it("handles storage throwing gracefully without crashing", () => {
    mockStorage.shouldThrow = true;

    expect(isStorageAvailable(mockStorage)).toBe(false);
    expect(getSavedItems(mockStorage)).toEqual([]);
    expect(isItemSaved("/projects/anything", mockStorage)).toBe(false);

    const addRes = addSavedItem({ kind: "project", path: "/projects/p", name: "P" }, mockStorage);
    expect(addRes.success).toBe(false);
    expect(addRes.error).toBeDefined();

    const rmRes = removeSavedItem("/projects/p", mockStorage);
    expect(rmRes.success).toBe(false);
    expect(rmRes.error).toBeDefined();
  });

  it("handles window.localStorage throwing SecurityError when site data is blocked (Must 2)", () => {
    // Stub window.localStorage getter to throw SecurityError (simulates Chrome/Safari with blocked cookies/storage)
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("The user denied permission to use Storage.", "SecurityError");
      },
    });

    expect(safeLocalStorage()).toBeNull();
    expect(getSavedHomesSnapshot()).toBe("[]");
    expect(isStorageAvailable()).toBe(false);
    expect(getSavedItems()).toEqual([]);
    expect(isItemSaved("/projects/anything")).toBe(false);

    const addRes = addSavedItem({ kind: "project", path: "/projects/p", name: "P" });
    expect(addRes.success).toBe(false);
    expect(addRes.error).toBe("Storage unavailable");

    const rmRes = removeSavedItem("/projects/p");
    expect(rmRes.success).toBe(false);
    expect(rmRes.error).toBe("Storage unavailable");
  });

  it("treats unknown storage version as unknown without overwriting (Nit)", () => {
    const futureV2Payload = {
      v: 2,
      items: [
        {
          kind: "project",
          path: "/projects/future-project",
          name: "Future Project",
          savedAt: new Date().toISOString(),
          notes: "Future field",
        },
      ],
    };
    mockStorage.setItem(SAVED_HOMES_STORAGE_KEY, JSON.stringify(futureV2Payload));

    // getSavedItems treats unknown v as []
    expect(getSavedItems(mockStorage)).toEqual([]);

    // addSavedItem refuses to overwrite unknown version
    const addRes = addSavedItem(
      { kind: "project", path: "/projects/new-project", name: "New Project" },
      mockStorage,
    );
    expect(addRes.success).toBe(false);
    expect(addRes.error).toBe("Unknown storage version");

    // removeSavedItem refuses to overwrite unknown version
    const rmRes = removeSavedItem("/projects/future-project", mockStorage);
    expect(rmRes.success).toBe(false);
    expect(rmRes.error).toBe("Unknown storage version");

    // Raw storage is untouched and preserved
    const raw = mockStorage.getItem(SAVED_HOMES_STORAGE_KEY);
    expect(raw).toBe(JSON.stringify(futureV2Payload));
  });

  it("strictly validates paths matching API slug rules (Nit)", () => {
    // Valid slugs
    expect(
      isValidSavedItem({
        kind: "project",
        path: "/projects/valid-slug",
        name: "Valid",
        savedAt: new Date().toISOString(),
      }),
    ).toBe(true);

    // Invalid slugs: leading hyphen, trailing hyphen, double hyphen
    expect(
      isValidSavedItem({
        kind: "project",
        path: "/projects/-invalid",
        name: "Invalid",
        savedAt: new Date().toISOString(),
      }),
    ).toBe(false);
    expect(
      isValidSavedItem({
        kind: "project",
        path: "/projects/invalid-",
        name: "Invalid",
        savedAt: new Date().toISOString(),
      }),
    ).toBe(false);
    expect(
      isValidSavedItem({
        kind: "project",
        path: "/projects/double--hyphen",
        name: "Invalid",
        savedAt: new Date().toISOString(),
      }),
    ).toBe(false);
    expect(
      isValidSavedItem({
        kind: "property",
        path: "/projects/valid-project/double--hyphen",
        name: "Invalid",
        savedAt: new Date().toISOString(),
      }),
    ).toBe(false);
  });

  it("announces 'Couldn't update saved homes in this browser' when removing a saved home fails (Task L1)", () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: mockStorage,
    });

    addSavedItem(
      { kind: "project", path: "/projects/luxury-villas", name: "Luxury Villas" },
      mockStorage,
    );

    const { container, getByRole } = render(
      React.createElement(SaveButton, {
        kind: "project",
        path: "/projects/luxury-villas",
        name: "Luxury Villas",
      }),
    );

    const button = getByRole("button", { name: /Saved Luxury Villas/i });
    expect(button).toBeDefined();

    // Cause storage write to fail during removal
    mockStorage.shouldThrow = true;

    act(() => {
      fireEvent.click(button);
    });

    const liveRegion = container.querySelector("[aria-live='polite']");
    expect(liveRegion?.textContent).toBe("Couldn't update saved homes in this browser");
  });
});

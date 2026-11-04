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
 * - storage throwing handled gracefully without crashing
 */
import { beforeEach, describe, expect, it } from "vitest";
import {
  addSavedItem,
  getSavedItems,
  isItemSaved,
  isStorageAvailable,
  MAX_SAVED_ITEMS,
  removeSavedItem,
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

  it("safely discards rubbish and malformed entries in storage", () => {
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
});

/**
 * Saved homes storage layer (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Requirements:
 *   - Stored in localStorage under one key ("empire_saved_homes").
 *   - List of `{ kind: "project" | "property", path, name, savedAt }`.
 *   - At most 50 items, newest first.
 *   - Duplicates collapse to one (updating position to newest).
 *   - Every read and write wrapped in try/catch so blocked or quota-exceeded storage fails safely.
 *   - Garbage / invalid entries in storage are discarded.
 *   - Browser only: no cookies, no accounts, nothing sent to the server.
 */

export const SAVED_HOMES_STORAGE_KEY = "empire_saved_homes";
export const MAX_SAVED_ITEMS = 50;
const SAVED_HOMES_EVENT = "empire:saved_homes";

export type SavedItemKind = "project" | "property";

export interface SavedItem {
  kind: SavedItemKind;
  /** Relative web path, e.g. "/projects/the-grand-residences" or "/projects/the-grand-residences/3-bhk". */
  path: string;
  /** Title or name of the project or property. */
  name: string;
  /** ISO 8601 timestamp string of when the item was saved. */
  savedAt: string;
}

export interface SaveOperationResult {
  success: boolean;
  items: SavedItem[];
  error?: string;
}

/**
 * Validates whether an unknown value conforms to the SavedItem interface.
 */
export function isValidSavedItem(val: unknown): val is SavedItem {
  if (!val || typeof val !== "object") return false;
  const item = val as Record<string, unknown>;
  const validKind = item.kind === "project" || item.kind === "property";
  const validPath = typeof item.path === "string" && item.path.startsWith("/");
  const validName = typeof item.name === "string" && item.name.trim().length > 0;
  const validSavedAt =
    typeof item.savedAt === "string" &&
    item.savedAt.length > 0 &&
    !Number.isNaN(Date.parse(item.savedAt));
  return validKind && validPath && validName && validSavedAt;
}

function resolveStorage(customStorage?: Storage): Storage | null {
  if (customStorage) return customStorage;
  if (typeof window !== "undefined" && window.localStorage) {
    return window.localStorage;
  }
  return null;
}

/**
 * Reads all saved items from localStorage.
 * Discards malformed items and caps list at MAX_SAVED_ITEMS.
 * Returns empty array if storage is blocked, throws, or is unavailable.
 */
export function getSavedItems(storage?: Storage): SavedItem[] {
  try {
    const s = resolveStorage(storage);
    if (!s) return [];
    const raw = s.getItem(SAVED_HOMES_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const validItems: SavedItem[] = [];
    for (const item of parsed) {
      if (isValidSavedItem(item)) {
        validItems.push(item);
        if (validItems.length >= MAX_SAVED_ITEMS) break;
      }
    }
    return validItems;
  } catch {
    return [];
  }
}

/**
 * Adds or updates an item in saved homes.
 * Newest first; duplicates collapse to one; max 50 items.
 */
export function addSavedItem(
  item: Omit<SavedItem, "savedAt"> & { savedAt?: string },
  storage?: Storage,
): SaveOperationResult {
  try {
    const s = resolveStorage(storage);
    if (!s) {
      return { success: false, items: [], error: "Storage unavailable" };
    }

    if (!item.path || typeof item.path !== "string" || !item.path.startsWith("/")) {
      throw new RangeError(`addSavedItem: invalid path ${item.path}`);
    }
    if (!item.name || typeof item.name !== "string" || !item.name.trim()) {
      throw new RangeError(`addSavedItem: invalid name ${item.name}`);
    }
    if (item.kind !== "project" && item.kind !== "property") {
      throw new RangeError(`addSavedItem: invalid kind ${item.kind}`);
    }

    const currentItems = getSavedItems(s);
    // Duplicates collapse to one: remove any existing entry with the same path
    const remaining = currentItems.filter((i) => i.path !== item.path);

    const newItem: SavedItem = {
      kind: item.kind,
      path: item.path,
      name: item.name.trim(),
      savedAt: item.savedAt || new Date().toISOString(),
    };

    // Newest first, capped at 50 items
    const updated = [newItem, ...remaining].slice(0, MAX_SAVED_ITEMS);
    s.setItem(SAVED_HOMES_STORAGE_KEY, JSON.stringify(updated));
    notifySavedHomesChanged();
    return { success: true, items: updated };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Storage error";
    return { success: false, items: [], error: msg };
  }
}

/**
 * Removes an item from saved homes by its relative path.
 */
export function removeSavedItem(path: string, storage?: Storage): SaveOperationResult {
  try {
    const s = resolveStorage(storage);
    if (!s) {
      return { success: false, items: [], error: "Storage unavailable" };
    }
    const currentItems = getSavedItems(s);
    const updated = currentItems.filter((i) => i.path !== path);
    s.setItem(SAVED_HOMES_STORAGE_KEY, JSON.stringify(updated));
    notifySavedHomesChanged();
    return { success: true, items: updated };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Storage error";
    return { success: false, items: [], error: msg };
  }
}

/**
 * Checks whether an item is already saved.
 */
export function isItemSaved(path: string, storage?: Storage): boolean {
  try {
    const s = resolveStorage(storage);
    if (!s) return false;
    const items = getSavedItems(s);
    return items.some((i) => i.path === path);
  } catch {
    return false;
  }
}

/**
 * Verifies whether localStorage is functioning without throwing (e.g. not blocked by private mode or quotas).
 */
export function isStorageAvailable(storage?: Storage): boolean {
  try {
    const s = resolveStorage(storage);
    if (!s) return false;
    const testKey = "__empire_test_storage__";
    s.setItem(testKey, "1");
    s.removeItem(testKey);
    return true;
  } catch {
    return false;
  }
}

/**
 * Subscribes to storage events and local custom events for saved homes updates.
 */
export function subscribeSavedHomes(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", callback);
  window.addEventListener(SAVED_HOMES_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(SAVED_HOMES_EVENT, callback);
  };
}

export function notifySavedHomesChanged(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SAVED_HOMES_EVENT));
  }
}

export function getSavedHomesSnapshot(): string {
  if (typeof window === "undefined" || !window.localStorage) return "[]";
  try {
    return window.localStorage.getItem(SAVED_HOMES_STORAGE_KEY) || "[]";
  } catch {
    return "[]";
  }
}

export function getServerSavedHomesSnapshot(): string {
  return "[]";
}

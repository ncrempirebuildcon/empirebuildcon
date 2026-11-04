/**
 * Saved homes storage layer (handbook/tasks/phase-5/5.7b-tools.md).
 *
 * Requirements:
 *   - Stored in localStorage under one key ("empire_saved_homes").
 *   - Stored as versioned schema: `{ v: 1, items: [...] }` (also supports reading bare v0 arrays).
 *   - List of `{ kind: "project" | "property", path, name, savedAt }`.
 *   - At most 50 items, newest first.
 *   - Duplicates collapse to one (updating position to newest).
 *   - Every read and write wrapped in safeLocalStorage / try-catch so blocked or quota-exceeded storage fails safely.
 *   - Paths strictly validated: `/projects/<slug>` for projects, `/projects/<slug>/<config>` for properties.
 *   - Browser only: no cookies, no accounts, nothing sent to the server.
 *
 * Collaborators: Antigravity <noreply@google.com>, Claude (review 1). Decisions: D-040, D-049.
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

export interface StoredSavedPayload {
  v: 1;
  items: SavedItem[];
}

export interface SaveOperationResult {
  success: boolean;
  items: SavedItem[];
  error?: string;
}

const PROJECT_PATH_REGEX = /^\/projects\/[a-z0-9-]+$/;
const PROPERTY_PATH_REGEX = /^\/projects\/[a-z0-9-]+\/[a-z0-9-]+$/;

/**
 * Accesses window.localStorage safely without throwing when site data or cookies are blocked.
 * (Must 2: Chrome / Safari private browsing throws SecurityError on window.localStorage access).
 */
export function safeLocalStorage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.localStorage;
  } catch {
    return null;
  }
}

/**
 * Validates whether an unknown value conforms to the SavedItem interface
 * with valid path format and matching kind.
 */
export function isValidSavedItem(val: unknown): val is SavedItem {
  if (!val || typeof val !== "object") return false;
  const item = val as Record<string, unknown>;

  const validKind = item.kind === "project" || item.kind === "property";
  if (!validKind) return false;

  const rawPath = item.path;
  if (typeof rawPath !== "string") return false;

  // Strict path format and kind matching (Nit: prevent protocol-relative '//evil.example' or mismatched kind)
  if (item.kind === "project" && !PROJECT_PATH_REGEX.test(rawPath)) return false;
  if (item.kind === "property" && !PROPERTY_PATH_REGEX.test(rawPath)) return false;

  const validName = typeof item.name === "string" && item.name.trim().length > 0;
  const validSavedAt =
    typeof item.savedAt === "string" &&
    item.savedAt.length > 0 &&
    !Number.isNaN(Date.parse(item.savedAt));

  return validName && validSavedAt;
}

function resolveStorage(customStorage?: Storage): Storage | null {
  if (customStorage) return customStorage;
  return safeLocalStorage();
}

/**
 * Reads all saved items from localStorage.
 * Handles both v1 (`{ v: 1, items }`) and v0 (`[...]`) storage payloads.
 * Discards malformed items, collapses duplicates, and caps list at MAX_SAVED_ITEMS.
 * Returns empty array if storage is blocked, throws, or is unavailable.
 */
export function getSavedItems(storage?: Storage): SavedItem[] {
  try {
    const s = resolveStorage(storage);
    if (!s) return [];
    const raw = s.getItem(SAVED_HOMES_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);

    let rawList: unknown[] = [];
    if (Array.isArray(parsed)) {
      rawList = parsed;
    } else if (
      parsed &&
      typeof parsed === "object" &&
      Array.isArray((parsed as Record<string, unknown>).items)
    ) {
      rawList = (parsed as Record<string, unknown>).items as unknown[];
    } else {
      return [];
    }

    const validItems: SavedItem[] = [];
    const seenPaths = new Set<string>();

    for (const item of rawList) {
      if (isValidSavedItem(item) && !seenPaths.has(item.path)) {
        seenPaths.add(item.path);
        validItems.push(item);
        if (validItems.length >= MAX_SAVED_ITEMS) break;
      }
    }
    return validItems;
  } catch {
    return [];
  }
}

function serializePayload(items: SavedItem[]): string {
  const payload: StoredSavedPayload = {
    v: 1,
    items,
  };
  return JSON.stringify(payload);
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

    if (!item.path || typeof item.path !== "string") {
      throw new RangeError(`addSavedItem: invalid path ${item.path}`);
    }
    if (item.kind === "project" && !PROJECT_PATH_REGEX.test(item.path)) {
      throw new RangeError(`addSavedItem: invalid project path ${item.path}`);
    }
    if (item.kind === "property" && !PROPERTY_PATH_REGEX.test(item.path)) {
      throw new RangeError(`addSavedItem: invalid property path ${item.path}`);
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
    s.setItem(SAVED_HOMES_STORAGE_KEY, serializePayload(updated));
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
    s.setItem(SAVED_HOMES_STORAGE_KEY, serializePayload(updated));
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

/**
 * Retrieves snapshot string for useSyncExternalStore safely without throwing when site data is blocked.
 * (Must 2: Chrome / Safari private browsing throws SecurityError on window.localStorage access).
 */
export function getSavedHomesSnapshot(): string {
  const s = safeLocalStorage();
  if (!s) return "[]";
  try {
    return s.getItem(SAVED_HOMES_STORAGE_KEY) || "[]";
  } catch {
    return "[]";
  }
}

export function getServerSavedHomesSnapshot(): string {
  return "[]";
}

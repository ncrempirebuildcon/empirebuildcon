/**
 * Stored visitor cookie consent choices (Phase 6 Task 6.1, Scope 1).
 *
 * Implements DPDP Act (2023) consent requirements, D-056:
 * - Stored in localStorage under "empire.consent".
 * - Shape: { v: 1, analytics: boolean, marketing: boolean, at: string }.
 *   "Necessary" is always on and not stored.
 * - Choices expire after 12 months (365 days), asking the visitor again.
 * - Missing, corrupt, unreadable, or wrong version yields null.
 * - Blocked or throwing storage retains choice in memory for the page session without crashing.
 * - Updates announced in the same tab via CustomEvent("empire:consent") and cross-tab via "storage".
 * - Task 6.3 relies strictly on these exported names.
 */

export const CONSENT_STORAGE_KEY = "empire.consent";
export const CONSENT_EVENT_NAME = "empire:consent";
export const OPEN_SETTINGS_EVENT_NAME = "empire:consent-open-settings";

const TWELVE_MONTHS_MS = 365 * 24 * 60 * 60 * 1000;

export interface Consent {
  v: 1;
  analytics: boolean;
  marketing: boolean;
  /** ISO 8601 date string when consent was granted/updated. */
  at: string;
}

/** In-memory fallback if localStorage throws or is unavailable (e.g. private browsing, blocked cookies). */
let memoryConsent: Consent | null = null;

/** Cached snapshot reference for useSyncExternalStore Object.is stability. */
let cachedSnapshot: Consent | null = null;
let lastRawValue: string | null = null;

/** Listeners registered via subscribe(). */
const subscribers = new Set<(c: Consent | null) => void>();
let isStorageListenerAttached = false;

function safeLocalStorage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.localStorage;
  } catch {
    return null;
  }
}

/** True when a write to storage succeeds, so a missing value means "not chosen". */
function storageWorks(storage: Storage): boolean {
  try {
    const probe = `${CONSENT_STORAGE_KEY}.probe`;
    storage.setItem(probe, "1");
    storage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

function parseConsent(raw: string | null): Consent | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw);
    if (!data || typeof data !== "object") return null;
    if (data.v !== 1) return null;
    if (typeof data.analytics !== "boolean" || typeof data.marketing !== "boolean") return null;
    if (typeof data.at !== "string") return null;

    const timestamp = new Date(data.at).getTime();
    if (Number.isNaN(timestamp)) return null;

    const ageMs = Date.now() - timestamp;
    if (ageMs > TWELVE_MONTHS_MS || ageMs < 0) {
      return null;
    }

    return {
      v: 1,
      analytics: data.analytics,
      marketing: data.marketing,
      at: data.at,
    };
  } catch {
    return null;
  }
}

/**
 * Reads the current consent choice.
 * Returns null if not chosen, corrupt, wrong version, expired (>12 months), or uninitialized.
 * Result is referentially stable across calls with the same storage value.
 */
export function readConsent(): Consent | null {
  const storage = safeLocalStorage();
  if (storage) {
    try {
      const raw = storage.getItem(CONSENT_STORAGE_KEY);
      if (raw === lastRawValue && cachedSnapshot !== null) {
        // The same stored value, unless it has expired during the visit (6.3 review).
        if (parseConsent(raw) !== null) return cachedSnapshot;
        cachedSnapshot = null;
      }
      lastRawValue = raw;
      cachedSnapshot = parseConsent(raw);
      if (cachedSnapshot) {
        memoryConsent = cachedSnapshot;
        return cachedSnapshot;
      }
      // WHY (6.1 review, Nit 2): storage works but holds no valid choice (cleared, or expired
      // during a long visit), so the visitor is asked again. The memory copy is only for
      // storage that can't be used at all.
      if (storageWorks(storage)) {
        memoryConsent = null;
        return null;
      }
    } catch {
      // Storage access or read threw; fall back to memory
    }
  }
  return memoryConsent;
}

/**
 * Writes the visitor's choice to storage (and in-memory fallback), notifying subscribers
 * and dispatching a CustomEvent on window.
 */
export function writeConsent(choice: { analytics: boolean; marketing: boolean }): Consent {
  const consent: Consent = {
    v: 1,
    analytics: Boolean(choice.analytics),
    marketing: Boolean(choice.marketing),
    at: new Date().toISOString(),
  };

  memoryConsent = consent;
  cachedSnapshot = consent;
  lastRawValue = JSON.stringify(consent);

  const storage = safeLocalStorage();
  if (storage) {
    try {
      storage.setItem(CONSENT_STORAGE_KEY, lastRawValue);
    } catch {
      // Quota exceeded or storage blocked; memoryConsent holds the choice
    }
  }

  // Same-tab window event
  if (typeof window !== "undefined") {
    try {
      window.dispatchEvent(new CustomEvent(CONSENT_EVENT_NAME, { detail: consent }));
    } catch {
      // Ignore if event dispatch fails in restricted environment
    }
  }

  // Notify direct subscribers
  subscribers.forEach((listener) => {
    try {
      listener(consent);
    } catch {
      // Subscriber error shouldn't crash caller
    }
  });

  return consent;
}

/**
 * Cross-tab storage listener to keep tabs in sync.
 */
function handleStorageEvent(event: StorageEvent) {
  if (event.key === CONSENT_STORAGE_KEY) {
    lastRawValue = event.newValue;
    const updated = parseConsent(event.newValue);
    cachedSnapshot = updated;
    memoryConsent = updated;
    subscribers.forEach((listener) => {
      try {
        listener(updated);
      } catch {
        // Ignore
      }
    });
  }
}

/**
 * Subscribes to consent updates (from writeConsent or cross-tab storage changes).
 * Returns an unsubscribe callback.
 */
export function subscribe(listener: (c: Consent | null) => void): () => void {
  subscribers.add(listener);

  if (typeof window !== "undefined" && !isStorageListenerAttached) {
    try {
      window.addEventListener("storage", handleStorageEvent);
      isStorageListenerAttached = true;
    } catch {
      // Ignore
    }
  }

  return () => {
    subscribers.delete(listener);
    if (subscribers.size === 0 && isStorageListenerAttached && typeof window !== "undefined") {
      try {
        window.removeEventListener("storage", handleStorageEvent);
        isStorageListenerAttached = false;
      } catch {
        // Ignore
      }
    }
  };
}

/**
 * Re-opens the consent banner on its settings view.
 */
export function openConsentSettings(): void {
  if (typeof window !== "undefined") {
    try {
      window.dispatchEvent(new CustomEvent(OPEN_SETTINGS_EVENT_NAME));
    } catch {
      // Ignore
    }
  }
}

/**
 * Reset memory state and subscribers. For testing only.
 */
export function resetConsentMemory(): void {
  memoryConsent = null;
  cachedSnapshot = null;
  lastRawValue = null;
  subscribers.clear();
  if (isStorageListenerAttached && typeof window !== "undefined") {
    try {
      window.removeEventListener("storage", handleStorageEvent);
    } catch {
      // Ignore
    }
    isStorageListenerAttached = false;
  }
}

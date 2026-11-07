// @vitest-environment jsdom
/**
 * Unit tests for consent storage (Phase 6 Task 6.1, Scope 1).
 *
 * Verifies:
 * - missing value, corrupt value, or wrong version returns null
 * - value older than 12 months returns null
 * - write then read returns stored consent
 * - storage throwing on read, on write, or on getter doesn't crash and holds in memory for current page
 * - subscribe fires on write and on storage event, and unsubscribe works
 * - openConsentSettings dispatches event
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CONSENT_STORAGE_KEY,
  type Consent,
  openConsentSettings,
  readConsent,
  resetConsentMemory,
  subscribe,
  writeConsent,
} from "../src/lib/consent";

class MockStorage implements Storage {
  private store: Map<string, string> = new Map();
  public shouldThrowOnGet = false;
  public shouldThrowOnSet = false;

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    if (this.shouldThrowOnGet) throw new Error("Blocked storage / SecurityError");
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    if (this.shouldThrowOnSet) throw new Error("QuotaExceededError or Blocked");
    this.store.set(key, value);
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
}

describe("Consent storage layer (Task 6.1 Scope 1)", () => {
  let mockStorage: MockStorage;
  let originalLocalStorage: Storage;

  beforeEach(() => {
    resetConsentMemory();
    mockStorage = new MockStorage();
    originalLocalStorage = window.localStorage;
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: mockStorage,
    });
  });

  afterEach(() => {
    resetConsentMemory();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: originalLocalStorage,
    });
  });

  it("returns null when no value is stored", () => {
    expect(readConsent()).toBeNull();
  });

  it("returns null for corrupt JSON or wrong version or malformed shape", () => {
    mockStorage.setItem(CONSENT_STORAGE_KEY, "invalid-json{{");
    expect(readConsent()).toBeNull();

    mockStorage.setItem(
      CONSENT_STORAGE_KEY,
      JSON.stringify({ v: 2, analytics: true, marketing: true, at: new Date().toISOString() }),
    );
    expect(readConsent()).toBeNull();

    mockStorage.setItem(
      CONSENT_STORAGE_KEY,
      JSON.stringify({ v: 1, analytics: "yes", marketing: true, at: new Date().toISOString() }),
    );
    expect(readConsent()).toBeNull();

    mockStorage.setItem(
      CONSENT_STORAGE_KEY,
      JSON.stringify({ v: 1, analytics: true, marketing: false, at: "not-a-date" }),
    );
    expect(readConsent()).toBeNull();
  });

  it("returns null for a choice older than 12 months (365 days)", () => {
    const thirteenMonthsAgo = new Date(Date.now() - 400 * 24 * 60 * 60 * 1000).toISOString();
    mockStorage.setItem(
      CONSENT_STORAGE_KEY,
      JSON.stringify({ v: 1, analytics: true, marketing: true, at: thirteenMonthsAgo }),
    );
    expect(readConsent()).toBeNull();
  });

  it("writes and reads back valid consent", () => {
    const written = writeConsent({ analytics: true, marketing: false });
    expect(written.v).toBe(1);
    expect(written.analytics).toBe(true);
    expect(written.marketing).toBe(false);
    expect(typeof written.at).toBe("string");

    const read = readConsent();
    expect(read).toEqual(written);
  });

  it("handles storage throwing on getter, read and write, retaining choice in memory", () => {
    // 1. Getter throws (SecurityError in private browsing)
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("SecurityError: Access is denied");
      },
    });

    expect(readConsent()).toBeNull();
    const memChoice = writeConsent({ analytics: false, marketing: true });
    expect(readConsent()).toEqual(memChoice);

    // 2. Restore mockStorage with getItem throwing
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: mockStorage,
    });
    mockStorage.shouldThrowOnGet = true;
    expect(readConsent()).toEqual(memChoice);

    // 3. setItem throwing
    mockStorage.shouldThrowOnGet = false;
    mockStorage.shouldThrowOnSet = true;
    const secondChoice = writeConsent({ analytics: true, marketing: true });
    expect(readConsent()).toEqual(secondChoice);
  });

  it("subscribe fires on writeConsent and on storage event, and unsubscribe works", () => {
    const listener = vi.fn();
    const unsubscribe = subscribe(listener);

    const consent = writeConsent({ analytics: true, marketing: true });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(consent);

    // Simulate cross-tab storage event
    const remoteConsent: Consent = {
      v: 1,
      analytics: false,
      marketing: false,
      at: new Date().toISOString(),
    };
    mockStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(remoteConsent));
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: CONSENT_STORAGE_KEY,
        newValue: JSON.stringify(remoteConsent),
      }),
    );
    expect(listener).toHaveBeenCalledTimes(2);
    expect(listener).toHaveBeenLastCalledWith(remoteConsent);

    // Unsubscribe
    unsubscribe();
    writeConsent({ analytics: true, marketing: false });
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("openConsentSettings dispatches custom event", () => {
    const onOpen = vi.fn();
    window.addEventListener("empire:consent-open-settings", onOpen);

    openConsentSettings();
    expect(onOpen).toHaveBeenCalledTimes(1);

    window.removeEventListener("empire:consent-open-settings", onOpen);
  });
});

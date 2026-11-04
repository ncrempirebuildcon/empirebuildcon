/**
 * Shared hook to detect client mounting for tools components (D-040, D-049).
 *
 * WHY: useSyncExternalStore avoids hydration mismatch warnings by returning false on the server
 * and during initial client hydration, then synchronizing to true on the client without triggering
 * extra cascading renders.
 *
 * Collaborators: Antigravity <noreply@google.com>, Claude (review 1). Decisions: D-040, D-049.
 */
import { useSyncExternalStore } from "react";

function noopSubscribe() {
  return () => {};
}

function getClientMounted() {
  return true;
}

function getServerMounted() {
  return false;
}

export function useMounted(): boolean {
  return useSyncExternalStore(noopSubscribe, getClientMounted, getServerMounted);
}

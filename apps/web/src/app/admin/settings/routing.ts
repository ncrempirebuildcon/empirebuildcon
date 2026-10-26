/**
 * Lead routing as the Settings form edits it (D-016, ARCHITECTURE §8 "Assignment",
 * apps/api leads/routing.py):
 *   - `single`: the person in `single_owner_user_id`, or the sales inbox when nobody is chosen;
 *   - `round_robin`: in turn through `round_robin_user_ids`, skipping anyone in
 *     `round_robin_paused_user_ids` ("in rotation" off). An empty list means every active sales
 *     user; the API's `lead_rotation` preview shows who that is;
 *   - `manual`: unassigned until an admin assigns.
 *
 * INVARIANT: an untouched rotation is never saved, so "empty = every active sales user" keeps
 * its meaning (new sales staff join the rotation) until someone actually changes the order.
 */

export const ROUTING_MODES = {
  single: "One person, or the sales inbox",
  round_robin: "In turn (round robin)",
  manual: "Nobody: an admin assigns each lead",
} as const;

export type RoutingMode = keyof typeof ROUTING_MODES;

export interface RoutingDraft {
  mode: RoutingMode;
  inbox_email: string;
  /** "" = nobody: leads wait in the sales inbox. */
  single_owner_user_id: string;
  /** The rotation, in order. */
  list: string[];
  /** In the list, but out of rotation for now. */
  paused: string[];
}

function ids(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((id): id is string => typeof id === "string") : [];
}

/**
 * The form's draft from the stored `lead_routing` group. With an empty stored list, the list
 * shown is the one the API applies (`effective`, from the rotation preview).
 */
export function routingDraft(stored: Record<string, unknown>, effective: string[]): RoutingDraft {
  const list = ids(stored.round_robin_user_ids);
  const mode = stored.mode;
  return {
    mode: mode === "round_robin" || mode === "manual" ? mode : "single",
    inbox_email: typeof stored.inbox_email === "string" ? stored.inbox_email : "",
    single_owner_user_id:
      typeof stored.single_owner_user_id === "string" ? stored.single_owner_user_id : "",
    list: list.length > 0 ? list : effective,
    paused: ids(stored.round_robin_paused_user_ids),
  };
}

const same = (a: string[], b: string[]) => a.join(",") === b.join(",");

/** Only the keys that changed, in the API's names; empty text is sent as null. */
export function routingPatch(draft: RoutingDraft, saved: RoutingDraft): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  if (draft.mode !== saved.mode) patch.mode = draft.mode;
  if (draft.inbox_email.trim() !== saved.inbox_email.trim()) {
    patch.inbox_email = draft.inbox_email.trim() || null;
  }
  if (draft.single_owner_user_id !== saved.single_owner_user_id) {
    patch.single_owner_user_id = draft.single_owner_user_id || null;
  }
  const paused = draft.paused.filter((id) => draft.list.includes(id));
  const pausedChanged = !same([...paused].sort(), [...saved.paused].sort());
  // WHY the list with any paused change: the API wants every paused id in the stored list, and
  // with an untouched (empty = every sales user) list there would be nothing to find them in.
  if (pausedChanged || !same(draft.list, saved.list)) patch.round_robin_user_ids = draft.list;
  if (pausedChanged) patch.round_robin_paused_user_ids = paused;
  return patch;
}

/** Switch one person in or out of the rotation (adding them to the end of the list if new). */
export function setInRotation(draft: RoutingDraft, id: string, on: boolean): RoutingDraft {
  const list = draft.list.includes(id) ? draft.list : on ? [...draft.list, id] : draft.list;
  const paused = on
    ? draft.paused.filter((other) => other !== id)
    : [...new Set([...draft.paused, id])];
  return { ...draft, list, paused };
}

/** Take one person out of the list altogether (review M3: always allowed, even if they left). */
export function removeFromRotation(draft: RoutingDraft, id: string): RoutingDraft {
  return {
    ...draft,
    list: draft.list.filter((other) => other !== id),
    paused: draft.paused.filter((other) => other !== id),
  };
}

const NON_OWNER_ROLES: Record<string, string> = {
  marketing: "Marketing",
  content_editor: "Content editors",
};

/**
 * Why a listed person is skipped when leads are given out, from the API's rotation preview
 * (`can_own: false`), or null when they can take leads. Routing already skips them; the CMS says
 * why, so someone can remove them (review M3).
 */
export function unusableReason(
  row: { can_own: boolean; role: string | null } | undefined,
): string | null {
  if (!row || row.can_own) return null;
  const role = row.role ? NON_OWNER_ROLES[row.role] : undefined;
  return role
    ? `Skipped: ${role} can't own leads.`
    : "Skipped: deactivated, or hasn't set a password yet.";
}

/**
 * The API's messages about the list, by the person they are about: `round_robin_user_ids.N`
 * names the Nth id of the list that was sent (the draft's list, in order).
 */
export function errorsByPerson(
  errors: Record<string, string>,
  list: readonly string[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [field, message] of Object.entries(errors)) {
    const match = /^round_robin_user_ids\.(\d+)$/.exec(field);
    const id = match ? list[Number(match[1])] : undefined;
    if (id) out[id] = message;
  }
  return out;
}

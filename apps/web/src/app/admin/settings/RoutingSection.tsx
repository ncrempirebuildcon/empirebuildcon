"use client";
/**
 * Settings → Lead routing (board NoirCmsSettings, D-016): how new leads are given out, the shared
 * sales inbox that gets every alert, and the round-robin table: the order (Move up/Move down via
 * ReorderList, so the keyboard and screen readers can reorder), open leads, an "In rotation"
 * switch per person, and who gets the next lead (the API's read-only preview, `lead_rotation`).
 * People who can own leads but aren't listed can be added. Rules for the draft: routing.ts.
 */
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Alert, Button, Chip, ReorderList, Select, Switch, TextField } from "@empire/ui";
import { api, call } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/labels";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { useLoad } from "@/components/admin/useLoad";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";
import { readOnlyReason, type SectionProps } from "./sections";
import {
  ROUTING_MODES,
  errorsByPerson,
  removeFromRotation,
  routingDraft,
  routingPatch,
  setInRotation,
  unusableReason,
  type RoutingDraft,
  type RoutingMode,
} from "./routing";

export function RoutingSection({ settings, canSave, onDirtyChange }: SectionProps) {
  // Lead owners need leads.read; roles without it (marketing) see the API's preview only.
  const owners = useLoad("settings:lead-owners", () =>
    call(api.GET("/api/v1/admin/lead-owners")).catch(() => null),
  );
  const rotation = useMemo(() => settings.data?.lead_rotation ?? [], [settings.data]);
  const [saved, setSaved] = useState<RoutingDraft>(() =>
    routingDraft(
      settings.groups.lead_routing ?? {},
      rotation.map((row) => row.user.id),
    ),
  );
  const [draft, setDraft] = useState<RoutingDraft>(saved);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState("");
  const patch = routingPatch(draft, saved);
  const dirty = Object.keys(patch).length > 0;
  useReportDirty(onDirtyChange, dirty);

  const people = useMemo(() => owners.data ?? [], [owners.data]);
  // The list as last sent, so `round_robin_user_ids.N` errors find their person.
  const [sentList, setSentList] = useState<string[]>([]);
  const nameOf = useCallback(
    (id: string) =>
      people.find((p) => p.id === id)?.name ??
      rotation.find((row) => row.user.id === id)?.user.name ??
      "Former user",
    [people, rotation],
  );
  const roleOf = useCallback(
    (id: string) => {
      const role =
        people.find((p) => p.id === id)?.role ?? rotation.find((r) => r.user.id === id)?.role;
      return role ? (ROLE_LABELS[role] ?? role) : "";
    },
    [people, rotation],
  );
  const others = useMemo(
    () =>
      people.filter((p) => !draft.list.includes(p.id)).sort((a, b) => a.name.localeCompare(b.name)),
    [draft.list, people],
  );
  // The API's messages about listed people go next to them; anything else about the list on top.
  const personErrors = errorsByPerson(errors, sentList);
  const listError = Object.entries(errors).find(
    ([field]) => field.startsWith("round_robin") && !/^round_robin_user_ids\.\d+$/.test(field),
  )?.[1];
  // A single owner who can't own leads any more (deactivated, demoted): routing already sends
  // their leads to the sales inbox; show who it is, so it can be changed (review M3).
  const staleOwner =
    owners.data &&
    draft.single_owner_user_id &&
    !people.some((p) => p.id === draft.single_owner_user_id)
      ? draft.single_owner_user_id
      : null;

  const set = (change: Partial<RoutingDraft>) => {
    setDraft((current) => ({ ...current, ...change }));
    setNotice(null);
  };

  async function save() {
    if (busy || !dirty) return;
    setBusy(true);
    setError(null);
    setErrors({});
    setSentList(draft.list);
    try {
      await settings.save({ lead_routing: patch });
      setSaved(draft);
      setNotice("Saved. New leads follow these rules from now on; earlier leads keep their owner.");
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't save lead routing."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      noValidate
      aria-label="Lead routing"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
      className="flex flex-col gap-4.5"
    >
      {!canSave ? <Alert tone="info">{readOnlyReason("routing", settings)}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice && !dirty ? <Alert tone="success">{notice}</Alert> : null}
      <fieldset disabled={!canSave || busy} className="grid min-w-0 gap-4 md:grid-cols-2">
        <legend className="sr-only">Lead routing</legend>
        <TextField
          label="Shared sales inbox"
          type="email"
          autoComplete="off"
          maxLength={254}
          placeholder="[sales@empirebuildcon.com]"
          value={draft.inbox_email}
          onChange={(event) => set({ inbox_email: event.target.value })}
          error={errors.inbox_email}
          hint="Every new lead is emailed here, with a link to open it in the CMS. Left empty, every active super-admin is emailed instead, so no lead goes unannounced."
          className="md:col-span-2"
        />
        <Select
          label="New leads go to"
          value={draft.mode}
          options={(Object.keys(ROUTING_MODES) as RoutingMode[]).map((mode) => ({
            value: mode,
            label: ROUTING_MODES[mode],
          }))}
          onChange={(event) =>
            set({
              mode:
                (Object.keys(ROUTING_MODES) as RoutingMode[]).find(
                  (mode) => mode === event.target.value,
                ) ?? draft.mode,
            })
          }
          error={errors.mode}
        />
        {draft.mode === "single" ? (
          <Select
            label="Owner of every new lead"
            value={draft.single_owner_user_id}
            placeholder="Nobody: leads wait in the sales inbox"
            options={[
              ...(staleOwner
                ? [{ value: staleOwner, label: `${nameOf(staleOwner)} (can't own leads now)` }]
                : []),
              ...people.map((p) => ({
                value: p.id,
                label: `${p.name} (${ROLE_LABELS[p.role] ?? p.role})`,
              })),
            ]}
            onChange={(event) => set({ single_owner_user_id: event.target.value })}
            error={errors.single_owner_user_id}
            hint={
              staleOwner
                ? "This person can't own leads any more, so new leads wait in the sales inbox. Choose someone else, or Nobody."
                : undefined
            }
          />
        ) : null}
      </fieldset>

      <section aria-labelledby="rotation-title" className="flex flex-col gap-2.5">
        <h3 id="rotation-title" className="text-base font-bold">
          Round-robin order
        </h3>
        <p className="text-caption text-muted">
          {draft.mode === "round_robin"
            ? "New leads go to the next person in rotation, then the next, in this order."
            : "Used when “In turn (round robin)” is chosen above."}{" "}
          Only people who can own leads (sales, admins and super-admins) can be listed.
        </p>
        {listError ? <p className="text-caption text-danger">{listError}</p> : null}
        {draft.list.length === 0 ? (
          <p className="text-small text-muted">
            Nobody is listed: in turn would go to every active sales user, oldest account first.
          </p>
        ) : (
          <ReorderList
            label="Round-robin order"
            items={draft.list}
            getKey={(id) => id}
            getLabel={nameOf}
            readOnly={!canSave}
            disabled={busy}
            onReorder={(list) => set({ list })}
            renderItem={(id, index) => {
              const row = rotation.find((r) => r.user.id === id);
              return (
                <PersonRow
                  name={`${index + 1}. ${nameOf(id)}`}
                  role={roleOf(id)}
                  detail={
                    row ? `${row.open_leads} open ${row.open_leads === 1 ? "lead" : "leads"}` : null
                  }
                  inRotation={!draft.paused.includes(id)}
                  disabled={!canSave || busy}
                  onToggle={(on) => setDraft((current) => setInRotation(current, id, on))}
                  onRemove={
                    canSave
                      ? () => {
                          setDraft((current) => removeFromRotation(current, id));
                          setNotice(null);
                        }
                      : undefined
                  }
                  switchContext={nameOf(id)}
                  reason={unusableReason(row)}
                  error={personErrors[id]}
                  badge={
                    draft.mode === "round_robin" && row?.gets_next && !dirty ? (
                      <Chip variant="scheduled">Gets the next lead</Chip>
                    ) : row && !row.can_own ? (
                      <Chip variant="archived">Can&apos;t own leads now</Chip>
                    ) : null
                  }
                />
              );
            }}
          />
        )}
        {canSave && others.length > 0 ? (
          <div className="flex flex-wrap items-end gap-2.5">
            <Select
              label="Add someone to the rotation"
              value={adding}
              placeholder="Choose a person"
              options={others.map((person) => ({
                value: person.id,
                label: `${person.name} (${ROLE_LABELS[person.role] ?? person.role})`,
              }))}
              onChange={(event) => setAdding(event.target.value)}
              className="min-w-0 flex-[1_1_260px]"
            />
            <Button
              variant="secondary"
              disabled={busy || !adding}
              className="mb-0.75"
              onClick={() => {
                setDraft((current) => setInRotation(current, adding, true));
                setAdding("");
              }}
            >
              Add to rotation
            </Button>
          </div>
        ) : null}
      </section>

      <ul className="flex flex-col gap-2 text-small">
        <li>
          Same phone number and project within 24 hours: linked to the earlier lead, with no second
          alert.
        </li>
        <li>The new owner gets an email when a lead is assigned to them.</li>
        <li>Marking a lead “Lost” asks for a reason.</li>
        <li className="text-muted">
          WhatsApp alerts for new leads: Phase 6 (needs the WhatsApp Business API).
        </li>
      </ul>

      {canSave ? (
        <div className="flex flex-wrap justify-end gap-2.5 border-t border-line pt-3.5">
          <Button
            variant="secondary"
            disabled={!dirty || busy}
            onClick={() => {
              setDraft(saved);
              setErrors({});
              setError(null);
            }}
          >
            Discard changes
          </Button>
          <Button type="submit" loading={busy} disabled={!dirty}>
            Save changes
          </Button>
        </div>
      ) : null}
    </form>
  );
}

function PersonRow({
  name,
  role,
  detail,
  inRotation,
  disabled,
  onToggle,
  onRemove,
  switchContext,
  reason,
  error,
  badge,
}: {
  name: string;
  role: string;
  detail: string | null;
  inRotation: boolean;
  disabled: boolean;
  onToggle: (on: boolean) => void;
  /** Takes them out of the list; absent for read-only roles. */
  onRemove?: () => void;
  switchContext: string;
  /** Why routing skips them (they can't own leads now), in words. */
  reason: string | null;
  /** The API's message about this person, from the last save. */
  error?: string;
  badge?: ReactNode;
}) {
  return (
    <span className="flex flex-col gap-1.5">
      <span className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <span className="flex min-w-0 flex-[1_1_160px] flex-col">
          <strong className="text-ivory">{name}</strong>
          <span className="text-xs text-muted">
            {role}
            {detail ? ` · ${detail}` : ""}
          </span>
        </span>
        <Switch
          checked={inRotation}
          disabled={disabled}
          onChange={onToggle}
          label="In rotation"
          stateText={{ on: "Yes", off: "No" }}
          context={switchContext}
        />
        {badge}
        {onRemove ? (
          <Button variant="tertiary" disabled={disabled} onClick={onRemove} className="min-h-11">
            Remove from rotation<span className="sr-only">: {switchContext}</span>
          </Button>
        ) : null}
      </span>
      {reason ? <span className="text-caption text-body">{reason}</span> : null}
      {error ? <span className="text-caption text-danger">{error}</span> : null}
    </span>
  );
}

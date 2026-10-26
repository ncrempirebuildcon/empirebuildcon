"use client";
/**
 * Acting on one site visit (boards NoirCmsVisits "Selected visit" and NoirCmsLead "Site visit"):
 * confirm the date and time agreed by phone, reschedule, mark it done or a no-show, cancel it,
 * and set who handles it and a note for the site team. Used on the calendar and the lead detail.
 *
 * How it works:
 *   1. The date and time are typed in India time and sent as one UTC instant (`istToIso`); they
 *      are shown back in IST (CODE_STYLE §4). A half-typed or past date is caught here first.
 *   2. Every action is one `PATCH /admin/site-visits/{id}` (SiteVisitUpdate) that also carries a
 *      changed "handled by" or note, so nothing typed is lost when a button is pressed.
 *   3. The result goes to the caller, which announces it in its polite live region ("Visit
 *      confirmed for Sat 24 Oct, 11:00 am.") and refreshes its list; the fields then follow the
 *      saved visit.
 *   4. Cancel asks first (ConfirmDialog); a cancelled, done or no-show visit is read-only.
 *
 * D-016: buyers request a day and a time of day; sales confirms the exact time by phone.
 * A confirm may also move the lead to "Site visit"; the API does and records that.
 */
import { useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Chip,
  ConfirmDialog,
  Select,
  TextField,
  Textarea,
  type SelectOption,
} from "@empire/ui";
import { istDate, istTime, istToIso, istToday, isCalendarDate } from "@empire/ui/format";
import { api, call, type Schema } from "@/lib/api";
import { formatDayLabel, formatVisitTime } from "@/lib/dates";
import { VISIT_STATUS, VISIT_STATUS_CHIP, slotLabel, type SiteVisit } from "@/lib/leads/labels";
import { isOpenVisit, visitWhen } from "@/lib/leads/visits";
import { problemMessage } from "@/lib/problems";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";

type VisitUpdate = Schema<"SiteVisitUpdate">;

export interface VisitEditorProps {
  visit: SiteVisit;
  /** Staff who can handle the visit; when empty the "Handled by" choice is not offered. */
  staff: SelectOption[];
  /** With `site_visits.manage` the visit can be changed; otherwise it is shown read-only. */
  canManage: boolean;
  onSaved: (visit: SiteVisit) => void;
  /**
   * Says what happened ("Visit confirmed for …") in the caller's polite live region. WHY the
   * caller's: the editor may be replaced by another visit's after a save, and its own region
   * would go with it before a screen reader read it.
   */
  onAnnounce: (message: string) => void;
  /** Whether the date, time, "handled by" or note differ from the saved visit (leave warning). */
  onDirtyChange?: (dirty: boolean) => void;
  /** Unique per page, for the field ids. */
  idPrefix: string;
  /** Extra content under the facts (e.g. "Open lead" and call links on the calendar). */
  children?: ReactNode;
}

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

export function VisitEditor({
  visit,
  staff,
  canManage,
  onSaved,
  onAnnounce,
  onDirtyChange,
  idPrefix,
  children,
}: VisitEditorProps) {
  const [date, setDate] = useState(() =>
    visit.confirmed_for ? istDate(visit.confirmed_for) : (visit.preferred_date ?? ""),
  );
  const [time, setTime] = useState(() => (visit.confirmed_for ? istTime(visit.confirmed_for) : ""));
  const [handledBy, setHandledBy] = useState(visit.handled_by?.id ?? "");
  const [notes, setNotes] = useState(visit.notes ?? "");
  const [errors, setErrors] = useState<{ date?: string; time?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [askCancel, setAskCancel] = useState(false);
  // The fields follow the saved visit whenever it changes (a save here, or a refresh).
  const [syncedAt, setSyncedAt] = useState(visit.updated_at);
  if (syncedAt !== visit.updated_at) {
    setSyncedAt(visit.updated_at);
    setDate(visit.confirmed_for ? istDate(visit.confirmed_for) : (visit.preferred_date ?? ""));
    setTime(visit.confirmed_for ? istTime(visit.confirmed_for) : "");
    setHandledBy(visit.handled_by?.id ?? "");
    setNotes(visit.notes ?? "");
  }
  const open = isOpenVisit(visit);
  const confirmed = visit.status === "confirmed";
  const timeChanged =
    !visit.confirmed_for ||
    istDate(visit.confirmed_for) !== date ||
    istTime(visit.confirmed_for) !== time;
  const detailsChanged =
    (visit.handled_by?.id ?? "") !== handledBy || (visit.notes ?? "") !== notes.trim();
  const scheduleTyped = visit.confirmed_for
    ? timeChanged
    : time !== "" || date !== (visit.preferred_date ?? "");
  useReportDirty(onDirtyChange, canManage && open && (detailsChanged || scheduleTyped));

  /** "Handled by" and the note, only when they differ from the saved visit (the API records
   * every changed field on the lead's timeline, so unchanged ones are left out). */
  function detailChanges(): VisitUpdate {
    const changes: VisitUpdate = {};
    if ((visit.handled_by?.id ?? "") !== handledBy) changes.handled_by_user_id = handledBy || null;
    if ((visit.notes ?? "") !== notes.trim()) changes.notes = notes.trim() || null;
    return changes;
  }

  /** The agreed instant, or null after showing what is wrong with the fields. */
  function agreedInstant(): string | null {
    const found: { date?: string; time?: string } = {};
    if (!isCalendarDate(date)) found.date = "Choose the date agreed with the buyer.";
    else if (date < istToday()) found.date = "Choose today or a later date.";
    if (!TIME_RE.test(time)) found.time = "Enter the time agreed with the buyer.";
    setErrors(found);
    if (found.date || found.time) {
      document.getElementById(`${idPrefix}-${found.date ? "date" : "time"}`)?.focus();
      return null;
    }
    return istToIso(date, time);
  }

  async function send(action: string, update: VisitUpdate, done: (saved: SiteVisit) => string) {
    if (busy) return;
    setBusy(action);
    setError(null);
    try {
      const saved = await call(
        api.PATCH("/api/v1/admin/site-visits/{id}", {
          params: { path: { id: visit.id } },
          body: { ...detailChanges(), ...update },
        }),
      );
      onAnnounce(done(saved));
      setAskCancel(false);
      onSaved(saved);
    } catch (err) {
      setError(problemMessage(err, "Couldn't save the visit."));
    } finally {
      setBusy(null);
    }
  }

  function confirmOrReschedule() {
    const instant = agreedInstant();
    if (!instant) return;
    void send(
      confirmed ? "reschedule" : "confirm",
      { status: "confirmed", confirmed_for: instant },
      (saved) =>
        `${confirmed ? "Visit moved to" : "Visit confirmed for"} ${
          saved.confirmed_for ? formatVisitTime(saved.confirmed_for) : visitWhen(saved)
        }.`,
    );
  }

  return (
    <div className="flex flex-col gap-3.5">
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3.5 gap-y-2 text-small">
        <dt className="text-muted">Status</dt>
        <dd>
          <Chip variant={VISIT_STATUS_CHIP[visit.status]}>{VISIT_STATUS[visit.status]}</Chip>
        </dd>
        <dt className="text-muted">Project</dt>
        <dd className="font-bold text-ivory">{visit.project.name}</dd>
        <dt className="text-muted">Requested</dt>
        <dd className="font-bold text-ivory">
          {visit.preferred_date ? formatDayLabel(visit.preferred_date) : "No date"} ·{" "}
          {slotLabel(visit.preferred_slot).toLowerCase()}
        </dd>
        {visit.confirmed_for ? (
          <>
            <dt className="text-muted">Agreed</dt>
            <dd className="font-bold text-ivory">{formatVisitTime(visit.confirmed_for)} IST</dd>
          </>
        ) : null}
        {!canManage || !open ? (
          <>
            <dt className="text-muted">Handled by</dt>
            <dd>{visit.handled_by?.name ?? "Not set"}</dd>
            {visit.notes ? (
              <>
                <dt className="text-muted">Note</dt>
                <dd className="[overflow-wrap:anywhere] whitespace-pre-line">{visit.notes}</dd>
              </>
            ) : null}
          </>
        ) : null}
      </dl>
      {children}

      {canManage && open ? (
        <form
          noValidate
          aria-label="Update this visit"
          className="flex flex-col gap-3.5"
          onSubmit={(event) => {
            event.preventDefault();
            confirmOrReschedule();
          }}
        >
          {!confirmed ? (
            <p className="text-caption text-gold-300">
              Not confirmed yet. Call the buyer to agree a time, then confirm it here.
            </p>
          ) : null}
          <div className="flex flex-wrap gap-3">
            <TextField
              id={`${idPrefix}-date`}
              label="Date agreed"
              type="date"
              min={istToday()}
              value={date}
              error={errors.date}
              onChange={(event) => setDate(event.target.value)}
              className="min-w-40 flex-[1_1_160px]"
            />
            <TextField
              id={`${idPrefix}-time`}
              label="Time agreed (IST)"
              type="time"
              step={300}
              value={time}
              error={errors.time}
              onChange={(event) => setTime(event.target.value)}
              className="min-w-32 flex-[1_1_130px]"
            />
          </div>
          {staff.length > 0 ? (
            <Select
              id={`${idPrefix}-handled-by`}
              label="Handled by"
              value={handledBy}
              placeholder="Not set"
              options={staff}
              onChange={(event) => setHandledBy(event.target.value)}
            />
          ) : null}
          <Textarea
            id={`${idPrefix}-notes`}
            label="Note for the site team (optional)"
            rows={3}
            maxLength={1000}
            placeholder="e.g. Coming with parents; wants to see the sample flat"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="grid grid-cols-1 gap-2 min-[360px]:grid-cols-2">
            <Button
              type="submit"
              loading={busy === "confirm" || busy === "reschedule"}
              disabled={confirmed && !timeChanged}
              className="min-[360px]:col-span-2"
            >
              {confirmed ? "Save new time" : "Confirm visit"}
            </Button>
            {confirmed ? (
              <>
                <Button
                  variant="secondary"
                  loading={busy === "completed"}
                  onClick={() =>
                    void send("completed", { status: "completed" }, () => "Visit marked done.")
                  }
                >
                  Mark done
                </Button>
                <Button
                  variant="secondary"
                  loading={busy === "no_show"}
                  onClick={() =>
                    void send("no_show", { status: "no_show" }, () => "Visit marked as a no-show.")
                  }
                >
                  Mark no-show
                </Button>
              </>
            ) : null}
            {detailsChanged ? (
              <Button
                variant="secondary"
                loading={busy === "details"}
                onClick={() => void send("details", {}, () => "Visit details saved.")}
              >
                Save note and owner
              </Button>
            ) : null}
            <Button
              variant="danger"
              className="min-[360px]:col-span-2"
              onClick={() => setAskCancel(true)}
            >
              Cancel this visit
            </Button>
          </div>
          <p className="border-t border-line pt-3 text-caption text-muted">
            Every change here is added to the lead&apos;s activity and the audit log.
          </p>
        </form>
      ) : null}

      <ConfirmDialog
        open={askCancel}
        title="Cancel this visit?"
        confirmLabel="Cancel visit"
        cancelLabel="Keep the visit"
        tone="danger"
        busy={busy === "cancelled"}
        error={askCancel ? error : null}
        onCancel={() => setAskCancel(false)}
        onConfirm={() => void send("cancelled", { status: "cancelled" }, () => "Visit cancelled.")}
      >
        The visit leaves the calendar. Do this when the buyer has called it off; the lead itself
        stays as it is.
      </ConfirmDialog>
    </div>
  );
}

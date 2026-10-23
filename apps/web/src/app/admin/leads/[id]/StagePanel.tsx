"use client";
/**
 * "Stage" on the lead detail (board NoirCmsLead): the six pipeline stages as toggle buttons, the
 * current one tagged "Current". Choosing another stage asks to confirm ("Move from Contacted to
 * Site visit. This is recorded in the activity."), and Lost asks for a reason first.
 *
 * Staff may move a lead back a stage to correct a mistake; the API records it as a backward
 * move. The new stage is announced in a polite live region once saved (DESIGN_SYSTEM §9).
 */
import { useState } from "react";
import { Alert, Button, LiveRegion, cx } from "@empire/ui";
import { updateLead } from "@/lib/leads/api";
import {
  LEAD_STATUS,
  LEAD_STATUS_ORDER,
  lostReasonLabel,
  type Lead,
  type LeadStatus,
} from "@/lib/leads/labels";
import { fieldErrors, problemMessage } from "@/lib/problems";
import { Panel } from "@/components/admin/states";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";
import {
  EMPTY_REASON,
  LostReasonFields,
  lostReasonBody,
  lostReasonError,
  type LostReasonValue,
} from "@/components/admin/leads/LostReasonFields";

export interface StagePanelProps {
  lead: Lead;
  /** With `leads.update` the stages can be changed; otherwise they are shown read-only. */
  canUpdate: boolean;
  onSaved: (lead: Lead) => void;
  /** Whether a new stage is chosen but not saved yet (for the leave warning). */
  onDirtyChange?: (dirty: boolean) => void;
}

export function StagePanel({ lead, canUpdate, onSaved, onDirtyChange }: StagePanelProps) {
  const [pending, setPending] = useState<LeadStatus>(lead.status);
  const [reason, setReason] = useState<LostReasonValue>(EMPTY_REASON);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  // WHY not a `key`: remounting on a new stage would also reset the live region before it
  // speaks. Instead the choice follows the saved stage whenever the lead changes (React's
  // "adjusting state when a prop changes" pattern).
  const [savedStatus, setSavedStatus] = useState(lead.status);
  if (savedStatus !== lead.status) {
    setSavedStatus(lead.status);
    setPending(lead.status);
  }
  const current = lead.status;
  const changing = pending !== current;
  useReportDirty(onDirtyChange, changing);
  const backward = LEAD_STATUS_ORDER.indexOf(pending) < LEAD_STATUS_ORDER.indexOf(current);

  function cancel() {
    setPending(current);
    setReason(EMPTY_REASON);
    setReasonError(null);
    setError(null);
  }

  async function save() {
    if (busy) return;
    const lostReason = pending === "lost" ? lostReasonBody(reason) : null;
    if (pending === "lost" && !lostReason) {
      setReasonError(lostReasonError(reason));
      document
        .getElementById(reason.choice === "other" ? "stage-reason-other" : "stage-reason")
        ?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setReasonError(null);
    try {
      const saved = await updateLead(
        lead.id,
        pending === "lost" && lostReason ? { status: pending, ...lostReason } : { status: pending },
      );
      setAnnouncement(`Stage changed to ${LEAD_STATUS[saved.status]}.`);
      setReason(EMPTY_REASON);
      onSaved(saved);
    } catch (err) {
      const fields = fieldErrors(err);
      const reasonMessage = fields.lost_reason_note ?? fields.lost_reason;
      if (reasonMessage) setReasonError(reasonMessage);
      else setError(problemMessage(err, "Couldn't change the stage."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      id="stage"
      title="Stage"
      actions={
        <span className="text-caption text-muted">
          Current: <strong className="text-gold-300">{LEAD_STATUS[current]}</strong>
        </span>
      }
    >
      <LiveRegion message={announcement} />
      {canUpdate ? (
        <div
          role="group"
          aria-label="Choose a stage"
          className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6"
        >
          {LEAD_STATUS_ORDER.map((status) => {
            const on = pending === status;
            return (
              <button
                key={status}
                type="button"
                aria-pressed={on}
                disabled={busy}
                onClick={() => {
                  setPending(status);
                  setReasonError(null);
                  setError(null);
                }}
                className={cx(
                  "flex min-h-12 flex-col items-center justify-center gap-px rounded-input border px-2 py-2 text-small",
                  on
                    ? "border-gold-500 bg-gold-tint font-extrabold text-gold-300"
                    : "border-line-strong bg-noir-700 font-semibold text-body hover:text-gold-300",
                )}
              >
                <span>{LEAD_STATUS[status]}</span>
                <span className={cx("text-xs font-bold", on ? "text-gold-400" : "text-muted")}>
                  {status === current ? (
                    <>
                      <span className="sr-only">, </span>Current
                    </>
                  ) : (
                    "\u00a0"
                  )}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <ol aria-label="Pipeline" className="flex flex-wrap gap-2">
          {LEAD_STATUS_ORDER.map((status) => (
            <li
              key={status}
              aria-current={status === current ? "step" : undefined}
              className={cx(
                "rounded-pill border px-3 py-1.5 text-caption",
                status === current
                  ? "border-gold-500 bg-gold-tint font-extrabold text-gold-300"
                  : "border-line text-muted",
              )}
            >
              {LEAD_STATUS[status]}
            </li>
          ))}
        </ol>
      )}

      {current === "lost" && lead.lost_reason && !changing ? (
        <p className="text-small">
          Lost because: <strong className="text-ivory">{lostReasonLabel(lead)}</strong>
        </p>
      ) : null}

      {canUpdate && changing ? (
        <div className="flex flex-col gap-3 rounded-input border border-gold-line-strong bg-noir-700 p-3.5">
          <p className="text-small">
            Move from <strong className="text-ivory">{LEAD_STATUS[current]}</strong> to{" "}
            <strong className="text-gold-300">{LEAD_STATUS[pending]}</strong>
            {backward ? ", back a stage" : ""}. This is recorded in the activity.
          </p>
          {pending === "lost" ? (
            <LostReasonFields
              idPrefix="stage"
              value={reason}
              onChange={(value) => {
                setReason(value);
                setReasonError(null);
              }}
              error={reasonError}
              disabled={busy}
            />
          ) : null}
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="flex flex-wrap gap-2.5">
            <Button loading={busy} onClick={() => void save()}>
              Save stage
            </Button>
            <Button variant="secondary" disabled={busy} onClick={cancel}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </Panel>
  );
}

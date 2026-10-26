"use client";
/**
 * "Activity" on the lead detail (board NoirCmsLead): add a note, then one timeline, newest
 * first, of notes and everything that happened to the lead (created, stage changes, owner
 * changes, visits, exports…), each with who did it and when (IST).
 *
 * Notes come from `/notes` (their text) and the rest from `/activity`; "note added" entries are
 * left out of the activity so a note never shows twice. A new note is announced and the list
 * refreshes.
 *
 * COMPLIANCE: notes are personal data; they are erased with the lead (`leads.erase`).
 */
import { useState, type FormEvent } from "react";
import { Button, LiveRegion, Textarea } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { describeActivity } from "@/lib/leads/activity";
import { ACTIVITY_TITLE } from "@/lib/leads/labels";
import { problemMessage } from "@/lib/problems";
import { ErrorPanel, Panel } from "@/components/admin/states";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";

type Note = Schema<"LeadNote">;
type Activity = Schema<"LeadActivity">;

interface Entry {
  id: string;
  at: string;
  title: string;
  detail: string | null;
  /** Who did it; null for an entry about a lead this viewer may not open (no actor shown). */
  by: string | null;
  note: boolean;
}

export interface LeadTimelineProps {
  leadId: string;
  notes: Note[] | undefined;
  activity: Activity[] | undefined;
  error: unknown;
  onRetry: () => void;
  canAddNote: boolean;
  /** Staff id → name, for owner changes. */
  nameOf: (userId: string) => string | null;
  /** Called after a note is saved, to refresh notes and activity. */
  onNoteAdded: () => Promise<void>;
  /** Whether a note is typed but not added yet (for the leave warning). */
  onDirtyChange?: (dirty: boolean) => void;
}

/** A repeat-enquiry line about a lead the viewer may not open: the API sends only a summary. */
function isGenericLink(item: Activity): boolean {
  const data = (item.data ?? {}) as Record<string, unknown>;
  return item.kind === "duplicate_linked" && typeof data.summary === "string";
}

function entries(
  notes: Note[],
  activity: Activity[],
  nameOf: LeadTimelineProps["nameOf"],
): Entry[] {
  const list: Entry[] = notes.map((note) => ({
    id: `note-${note.id}`,
    at: note.created_at,
    title: "Note",
    detail: note.body,
    by: note.author.name,
    note: true,
  }));
  for (const item of activity) {
    if (item.kind === "note_added") continue;
    list.push({
      id: `activity-${item.id}`,
      at: item.created_at,
      title: ACTIVITY_TITLE[item.kind] ?? item.kind,
      detail: describeActivity(item, nameOf),
      by: isGenericLink(item) ? null : (item.actor?.name ?? "System"),
      note: false,
    });
  }
  return list.sort((a, b) => b.at.localeCompare(a.at));
}

export function LeadTimeline({
  leadId,
  notes,
  activity,
  error,
  onRetry,
  canAddNote,
  nameOf,
  onNoteAdded,
  onDirtyChange,
}: LeadTimelineProps) {
  const [draft, setDraft] = useState("");
  useReportDirty(onDirtyChange, draft.trim() !== "");
  const [busy, setBusy] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const body = draft.trim();
    if (!body) {
      setNoteError("Write the note first.");
      return;
    }
    setBusy(true);
    setNoteError(null);
    try {
      await call(
        api.POST("/api/v1/admin/leads/{id}/notes", {
          params: { path: { id: leadId } },
          body: { body },
        }),
      );
      setDraft("");
      setAnnouncement("Note added.");
      await onNoteAdded();
    } catch (err) {
      setNoteError(problemMessage(err, "Couldn't add the note."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel id="activity" title="Activity" className="min-w-0">
      <LiveRegion message={announcement} />
      {canAddNote ? (
        <form noValidate aria-label="New note" onSubmit={addNote} className="flex flex-col gap-2">
          <Textarea
            id="note-input"
            label="Add a note"
            rows={2}
            maxLength={4000}
            placeholder="e.g. Prefers a weekend visit, call after 6 pm"
            hint="Notes are visible to the lead's owner and admins."
            value={draft}
            error={noteError ?? undefined}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Button type="submit" loading={busy} className="self-start">
            Add note
          </Button>
        </form>
      ) : null}
      {error ? (
        <ErrorPanel
          message={problemMessage(error, "Couldn't load the activity.")}
          onRetry={onRetry}
        />
      ) : !notes || !activity ? (
        <p className="text-small text-muted" role="status">
          Loading the activity…
        </p>
      ) : (
        <Timeline items={entries(notes, activity, nameOf)} />
      )}
    </Panel>
  );
}

function Timeline({ items }: { items: Entry[] }) {
  if (items.length === 0) return <p className="text-small">Nothing has happened yet.</p>;
  return (
    <ol aria-label="Timeline, newest first" className="flex flex-col">
      {items.map((item) => (
        <li
          key={item.id}
          className="grid grid-cols-[18px_minmax(0,1fr)] gap-3 border-t border-line py-2.5"
        >
          <span
            aria-hidden="true"
            className={`mt-1.5 ml-1 size-2.5 rounded-pill ${item.note ? "bg-ivory" : "bg-gold-500"}`}
          />
          <div className="flex flex-col gap-0.5 text-small">
            <div className="flex flex-wrap justify-between gap-x-2.5">
              <strong className="text-ivory">{item.title}</strong>
              <time dateTime={item.at} className="text-xs text-muted tabular-nums">
                {formatDateTime(item.at)}
              </time>
            </div>
            {item.detail ? (
              <span className="[overflow-wrap:anywhere] whitespace-pre-line">{item.detail}</span>
            ) : null}
            {item.by ? <span className="text-xs text-muted">{item.by}</span> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

"use client";
/**
 * The upload queue behind every media uploader (drop zone, "Upload QR image", floor plans,
 * progress photos, share image): checks each file, sends it on the right path, tracks progress,
 * and lets the user cancel.
 *
 * How it works:
 *   1. `add(files)` checks every file at once (lib/media/files.ts). A refused file becomes a
 *      failed row with the reason, and is never sent.
 *   2. Accepted files wait in a queue and are sent one at a time (photos through the API, videos
 *      and documents direct to the store; lib/media/upload.ts), so a big batch doesn't trip the
 *      upload rate limit or swamp a slow connection.
 *   3. Each row shows its phase and percentage. Cancel aborts the transfer. Once every byte has
 *      been sent (`xhr.upload.onload`), the row moves to "Saving…" and Cancel is no longer
 *      offered: the server finishes on its own and may already be replacing the old item.
 *   4. After a file is saved, `onUploaded` runs (usually re-reading the project so the new item
 *      shows in its list), then the row disappears and a polite message says where it went.
 *   5. WHY `reconcile`: a Cancel pressed in the instant the last bytes left can lose the race,
 *      so the server saves a file the screen calls cancelled. After any cancel of a file that
 *      had started sending, the owner is re-read, so the list shows what was really saved.
 *
 * Accessibility: progress is a `role="progressbar"` per row (UploadQueue.tsx); start, finish and
 * failure are announced through `message` (a polite live region). Focus is never moved by an
 * upload, so the user stays where they were (spec: "focus is kept after upload").
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { checkFile, formatBytes, type MediaKind } from "@/lib/media/files";
import type { HonestLabel } from "@/lib/media/labels";
import type { ImageEncoding } from "@/lib/media/resize";
import { problemMessage } from "@/lib/problems";
import {
  UploadCancelled,
  uploadDirect,
  uploadPhoto,
  type AttachTarget,
  type Media,
  type UploadPhase,
} from "@/lib/media/upload";

export type JobState = UploadPhase | "waiting" | "failed" | "cancelled";

export interface UploadJob {
  id: string;
  name: string;
  kind: MediaKind | null;
  state: JobState;
  loaded: number;
  total: number;
  error: string | null;
}

/** Where a file of each kind goes, and how it is saved. */
export interface UploadPlan {
  /** Kinds this uploader takes (others are refused with a clear message). */
  kinds: readonly MediaKind[];
  /** The owner and role for a file of this kind, or null to keep it unattached. */
  targetFor: (kind: MediaKind) => AttachTarget | null;
  /** How photos are encoded in the browser: "photo" (default), "qr" or "plan" (resize.ts). */
  encoding?: ImageEncoding;
  /** The honest label to save with each photo, when the place says what it is. */
  photoLabel?: PhotoLabel;
  /** Words for the success message, e.g. "Photos" or "the RERA QR code". */
  destinationFor?: (kind: MediaKind) => string;
  /**
   * A narrower rule for this place (e.g. the brochure is a PDF): the refusal, or null. Checked
   * first, so the message names what this place takes rather than every allowed type.
   */
  extraCheck?: (file: File) => string | null;
}

/** An honest label (and month) sent with a photo, so it can be shown straight away. */
export interface PhotoLabel {
  label: HonestLabel;
  /** First day of the month; required with "progress_photo". */
  labelMonth?: string;
}

export interface UseUploadsOptions {
  plan: UploadPlan;
  /** Runs after each file is saved (e.g. re-read the project). */
  onUploaded: (media: Media, kind: MediaKind) => Promise<unknown> | void;
  /** Re-reads the owner after a cancel that may have raced the save (step 5). */
  reconcile?: () => Promise<unknown>;
}

interface Pending {
  job: UploadJob;
  file: File;
  kind: MediaKind;
  mimeType: string;
  controller: AbortController;
  /** This batch's label, overriding the plan's (the Media tab asks per batch). */
  photoLabel?: PhotoLabel;
}

const KIND_LIST: Record<MediaKind, string> = {
  image: "Photos",
  video: "Videos",
  document: "Documents",
};

let counter = 0;
const nextId = () => `upload-${Date.now().toString(36)}-${(counter += 1)}`;

export function useUploads({ plan, onUploaded, reconcile }: UseUploadsOptions) {
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [message, setMessage] = useState("");
  const queue = useRef<Pending[]>([]);
  const running = useRef(false);
  const controllers = useRef(new Map<string, AbortController>());
  // WHY refs: the queue loop outlives renders; it must call the latest plan and callback.
  const planRef = useRef(plan);
  const onUploadedRef = useRef(onUploaded);
  const reconcileRef = useRef(reconcile);
  useEffect(() => {
    planRef.current = plan;
    onUploadedRef.current = onUploaded;
    reconcileRef.current = reconcile;
  });
  useEffect(() => {
    const live = controllers.current;
    // Leaving the page cancels whatever is still being sent.
    return () => live.forEach((controller) => controller.abort());
  }, []);

  const patch = useCallback((id: string, change: Partial<UploadJob>) => {
    setJobs((current) => current.map((job) => (job.id === id ? { ...job, ...change } : job)));
  }, []);

  const runOne = useCallback(
    async (item: Pending) => {
      const { job, file, kind, mimeType, controller } = item;
      const current = planRef.current;
      const target = current.targetFor(kind);
      const photoLabel = item.photoLabel ?? current.photoLabel;
      let started = false;
      const callbacks = {
        signal: controller.signal,
        onPhase: (state: UploadPhase) => {
          if (state === "uploading") started = true;
          patch(job.id, { state });
        },
        onProgress: (loaded: number, total: number) => patch(job.id, { loaded, total }),
      };
      try {
        const media =
          kind === "image"
            ? await uploadPhoto(
                file,
                {
                  target: target ?? undefined,
                  encoding: current.encoding,
                  label: photoLabel?.label,
                  labelMonth: photoLabel?.labelMonth,
                },
                callbacks,
              )
            : await uploadDirect(file, { kind, mimeType, target: target ?? undefined }, callbacks);
        patch(job.id, { state: "saving" });
        try {
          await onUploadedRef.current(media, kind);
        } catch {
          // WHY not an upload error: the file is saved; only the follow-up (its label or the
          // refresh) failed, and uploading it again would add it twice.
          patch(job.id, {
            state: "failed",
            error: `${file.name} was uploaded, but the list couldn't be refreshed. Reload the page to see it.`,
          });
          setMessage(`${file.name} was uploaded, but the list couldn't be refreshed.`);
          return;
        }
        setJobs((all) => all.filter((j) => j.id !== job.id));
        const where = current.destinationFor?.(kind) ?? KIND_LIST[kind];
        setMessage(`${file.name} was uploaded to ${where}.`);
      } catch (err) {
        if (err instanceof UploadCancelled) {
          patch(job.id, { state: "cancelled", error: null });
          setMessage(`The upload of ${file.name} was cancelled.`);
          if (started) await reconcileRef.current?.().catch(() => undefined); // 5
          return;
        }
        const text = problemMessage(err, `Couldn't upload ${file.name}.`);
        patch(job.id, { state: "failed", error: text });
        setMessage(`Couldn't upload ${file.name}. ${text}`);
      } finally {
        controllers.current.delete(job.id);
      }
    },
    [patch],
  );

  const drain = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    try {
      while (queue.current.length > 0) {
        const item = queue.current.shift();
        if (item && !item.controller.signal.aborted) await runOne(item);
      }
    } finally {
      running.current = false;
    }
  }, [runOne]);

  /**
   * Checks and queues files; returns how many were accepted.
   * @param photoLabel The honest label for this batch's photos (overrides the plan's).
   */
  const add = useCallback(
    (files: readonly File[], photoLabel?: PhotoLabel): number => {
      const kinds = planRef.current.kinds;
      const fresh: UploadJob[] = [];
      let accepted = 0;
      for (const file of files) {
        const extra = planRef.current.extraCheck?.(file);
        const check = extra ? ({ ok: false, message: extra } as const) : checkFile(file, kinds);
        const job: UploadJob = {
          id: nextId(),
          name: file.name,
          kind: check.ok ? check.kind : null,
          state: check.ok ? "waiting" : "failed",
          loaded: 0,
          total: file.size,
          error: check.ok ? null : check.message,
        };
        fresh.push(job);
        if (check.ok) {
          accepted += 1;
          const controller = new AbortController();
          controllers.current.set(job.id, controller);
          queue.current.push({
            job,
            file,
            kind: check.kind,
            mimeType: check.mimeType,
            controller,
            photoLabel,
          });
        }
      }
      setJobs((current) => [...current.filter((j) => j.state !== "cancelled"), ...fresh]);
      const refused = fresh.length - accepted;
      setMessage(
        [
          accepted > 0 ? `Uploading ${accepted} ${accepted === 1 ? "file" : "files"}.` : "",
          refused > 0
            ? `${refused} ${refused === 1 ? "file was" : "files were"} not accepted; see the list.`
            : "",
        ]
          .filter(Boolean)
          .join(" "),
      );
      void drain();
      return accepted;
    },
    [drain],
  );

  const cancel = useCallback((id: string) => {
    controllers.current.get(id)?.abort();
    queue.current = queue.current.filter((item) => item.job.id !== id);
    setJobs((current) =>
      current.map((job) =>
        job.id === id && job.state === "waiting" ? { ...job, state: "cancelled" } : job,
      ),
    );
  }, []);

  const dismiss = useCallback((id: string) => {
    setJobs((current) => current.filter((job) => job.id !== id));
  }, []);

  const busy = jobs.some((job) => !["failed", "cancelled"].includes(job.state));
  return { jobs, add, cancel, dismiss, message, busy };
}

export type Uploads = ReturnType<typeof useUploads>;

/** "1.2 of 4.0 MB" for a job in flight. */
export function progressText(job: UploadJob): string {
  return `${formatBytes(job.loaded)} of ${formatBytes(job.total)}`;
}

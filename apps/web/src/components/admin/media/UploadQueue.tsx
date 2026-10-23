"use client";
/**
 * The rows under an uploader: one per file being sent, with its progress, Cancel while it is
 * being sent, and Dismiss for a file that failed or was cancelled. Successful uploads leave the
 * list (the item appears in its media list instead) and are announced in `LiveRegion`.
 *
 * Accessibility: each row's bar is a named `role="progressbar"`; buttons carry the file name
 * ("Cancel tower.jpg"); a refusal is shown in words, in the danger colour and with a ✕ mark.
 */
import { Button, LiveRegion, ProgressBar, cx } from "@empire/ui";
import { progressText, type UploadJob, type Uploads } from "./useUploads";

const STATE_TEXT: Record<UploadJob["state"], string> = {
  waiting: "Waiting",
  preparing: "Preparing…",
  uploading: "Uploading",
  saving: "Saving…",
  failed: "Not uploaded",
  cancelled: "Cancelled",
};

function percent(job: UploadJob): number | null {
  if (job.state === "uploading" && job.total > 0) return (job.loaded / job.total) * 100;
  if (job.state === "saving") return 100;
  if (job.state === "waiting") return 0;
  return null;
}

export function UploadQueue({ uploads, className }: { uploads: Uploads; className?: string }) {
  const { jobs, cancel, dismiss, message } = uploads;
  return (
    <>
      {jobs.length > 0 ? (
        <ul aria-label="Uploads" className={cx("flex flex-col gap-2", className)}>
          {jobs.map((job) => {
            const ended = job.state === "failed" || job.state === "cancelled";
            const canCancel = ["waiting", "preparing", "uploading"].includes(job.state);
            return (
              <li
                key={job.id}
                className={cx(
                  "flex flex-wrap items-center gap-3 rounded-tile border bg-noir-900 px-3.5 py-2.5",
                  job.state === "failed" ? "border-danger" : "border-line",
                )}
              >
                <div className="flex min-w-0 flex-[1_1_220px] flex-col gap-1.5">
                  <span className="flex flex-wrap items-baseline gap-x-2 text-small">
                    <strong className="min-w-0 text-ivory [overflow-wrap:anywhere]">
                      {job.name}
                    </strong>
                    <span
                      className={cx(
                        "text-caption",
                        job.state === "failed" ? "text-danger" : "text-muted",
                      )}
                    >
                      {job.state === "failed" ? <span aria-hidden="true">✕ </span> : null}
                      {STATE_TEXT[job.state]}
                      {job.state === "uploading" ? ` · ${progressText(job)}` : null}
                    </span>
                  </span>
                  {ended ? (
                    job.error ? (
                      <span className="text-caption text-danger">{job.error}</span>
                    ) : null
                  ) : (
                    <ProgressBar
                      value={percent(job)}
                      label={`Uploading ${job.name}`}
                      valueText={
                        job.state === "uploading" ? progressText(job) : STATE_TEXT[job.state]
                      }
                    />
                  )}
                </div>
                {canCancel ? (
                  <Button
                    variant="secondary"
                    aria-label={`Cancel ${job.name}`}
                    onClick={() => cancel(job.id)}
                  >
                    Cancel
                  </Button>
                ) : ended ? (
                  <Button
                    variant="tertiary"
                    className="min-h-11"
                    aria-label={`Dismiss ${job.name}`}
                    onClick={() => dismiss(job.id)}
                  >
                    Dismiss
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
      <LiveRegion message={message} />
    </>
  );
}

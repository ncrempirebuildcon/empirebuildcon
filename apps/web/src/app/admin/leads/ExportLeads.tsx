"use client";
/**
 * "Export CSV" for the list on screen (board NoirCmsLeads; `GET /admin/leads/export.csv`, needs
 * `leads.export`). It asks first, because the file holds personal data and the export is logged.
 *
 * How it works:
 *   1. The ConfirmDialog says what the file contains and that the export is written to the audit
 *      log with the filters.
 *   2. The file is fetched with the session cookie and the CSRF token, checked, turned into a
 *      temporary object URL and saved through an `<a download>` named by the API
 *      (Content-Disposition), else "empire-leads-<date>.csv"; the URL is revoked afterwards.
 *   3. A refusal (too many rows, no permission) is shown in the dialog in the API's words.
 *
 * WHY fetch and not a plain link: a link can't send the CSRF header, and it would save an error
 * response as a ".csv" file; this way staff see the reason and the file is offered only when real.
 * COMPLIANCE: the CSV is personal data (DPDP Act); the API audits every export (SECURITY.md §8).
 */
import { useState } from "react";
import { Button, ConfirmDialog } from "@empire/ui";
import { ProblemError, isProblem } from "@empire/api-client";
import { istToday } from "@empire/ui/format";
import { currentCsrfToken } from "@/lib/api";
import { exportHref, type LeadFilters } from "@/lib/leads/filters";
import { problemMessage } from "@/lib/problems";
import { SIGN_IN_PATH } from "@/lib/routes";

/** The file name from `Content-Disposition: attachment; filename="…"`, if it is a safe one. */
function fileName(header: string | null): string {
  const match = header ? /filename="?([A-Za-z0-9._-]+\.csv)"?/i.exec(header) : null;
  return match?.[1] ?? `empire-leads-${istToday()}.csv`;
}

async function download(href: string): Promise<void> {
  // SECURITY: the export needs the session's CSRF token even though it is a GET (it writes an
  // audit row and timeline lines), so a link on another site can't start a download of personal
  // data (SECURITY.md §3). That is also why this is a fetch and not a plain link.
  const token = currentCsrfToken();
  const response = await fetch(href, {
    credentials: "include",
    headers: token ? { "X-CSRF-Token": token } : undefined,
  });
  if (response.status === 401) window.location.assign(SIGN_IN_PATH);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new ProblemError(
      isProblem(body) ? body : { title: response.statusText, status: response.status },
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName(response.headers.get("Content-Disposition"));
  document.body.append(link);
  link.click();
  link.remove();
  // WHY a delay: revoking at once can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

export function ExportLeads({ filters, filtered }: { filters: LeadFilters; filtered: boolean }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await download(exportHref(filters));
      setOpen(false);
    } catch (err) {
      setError(problemMessage(err, "Couldn't export the leads."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        variant="secondary"
        aria-describedby="export-note"
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
      >
        Export CSV
      </Button>
      <ConfirmDialog
        open={open}
        title="Export these leads?"
        confirmLabel="Download CSV"
        busy={busy}
        error={error}
        onCancel={() => setOpen(false)}
        onConfirm={() => void confirm()}
      >
        <p className="mb-2">
          The file contains personal data: names, mobile numbers, emails and messages of{" "}
          {filtered ? "every lead that matches the current filters" : "every lead you can see"}, up
          to 50,000 rows.
        </p>
        <p className="mb-2">
          The export is written to the audit log with your name, the filters and the number of rows.
        </p>
        <p>Keep the file on a work device and delete it when you are done.</p>
      </ConfirmDialog>
    </>
  );
}

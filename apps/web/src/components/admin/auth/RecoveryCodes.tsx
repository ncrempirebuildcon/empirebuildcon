"use client";
/**
 * Recovery codes, shown once (board NoirCmsLogin's set-up step): the list, "Copy codes",
 * "Download as text", and an "I've saved them" box that must be ticked before moving on.
 *
 * SECURITY (SECURITY.md §1): the codes exist only in this component's memory while it is on
 * screen. They are never stored in the browser, put in the address, the title or a log, and the
 * API never returns them again. The download is made in memory (a Blob) and its object URL is
 * revoked straight after the click.
 */
import { useState } from "react";
import { Alert, Button, Checkbox, CodeList } from "@empire/ui";

/** The text file's contents: a short heading, then one code per line. */
export function recoveryCodesText(codes: readonly string[], email: string): string {
  return [
    `Empire CMS recovery codes for ${email}`,
    "Each code works once, instead of a code from your authenticator app.",
    "Keep this file somewhere safe and private.",
    "",
    ...codes,
    "",
  ].join("\n");
}

export function RecoveryCodes({
  codes,
  email,
  onDone,
  doneLabel,
}: {
  codes: readonly string[];
  email: string;
  /** Called once the person ticked "I've saved them" and pressed the button. */
  onDone: () => void;
  doneLabel: string;
}) {
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function copy() {
    setError(null);
    try {
      await navigator.clipboard.writeText(codes.join("\n"));
      setMessage("Codes copied. Paste them into your password manager.");
    } catch {
      setMessage(null);
      setError("Copying isn't allowed here. Download them as a text file instead.");
    }
  }

  function download() {
    setError(null);
    const blob = new Blob([recoveryCodesText(codes, email)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "empire-cms-recovery-codes.txt";
    document.body.append(link);
    link.click();
    link.remove();
    // SECURITY: the codes don't stay reachable through a blob: address for long. WHY a delay:
    // revoking at once can cancel the download before the browser has read the file (the leads
    // export does the same).
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
    setMessage("Downloaded empire-cms-recovery-codes.txt.");
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-small">
        If you lose your phone, each of these codes lets you sign in once instead of a code from the
        app. <strong className="text-ivory">They are shown only now.</strong> Save them in a
        password manager or print them, and keep them private.
      </p>
      <CodeList label="Recovery codes" codes={codes} />
      <div className="flex flex-wrap gap-2.5">
        <Button variant="secondary" onClick={() => void copy()}>
          Copy codes
        </Button>
        <Button variant="secondary" onClick={download}>
          Download as text
        </Button>
      </div>
      {message ? <Alert tone="success">{message}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Checkbox
        checked={saved}
        onChange={(event) => setSaved(event.target.checked)}
        label="I've saved my recovery codes somewhere safe"
      />
      <Button disabled={!saved} onClick={onDone} className="w-full">
        {doneLabel}
      </Button>
    </div>
  );
}

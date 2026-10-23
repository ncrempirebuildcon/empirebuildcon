"use client";
/**
 * "Remove" for a single attached file (the brochure, the RERA QR code on a draft, a floor plan,
 * the share image): asks in a ConfirmDialog, DELETEs the link (the file stays in the library),
 * re-reads the owner and moves focus to `focusAfter`, because this button disappears.
 */
import { useState } from "react";
import { Button, ConfirmDialog } from "@empire/ui";
import { api, call } from "@/lib/api";
import { problemMessage } from "@/lib/problems";

export interface DetachButtonProps {
  linkId: string;
  /** The file's title, for the button's name and the question. */
  title: string;
  /** "project", "configuration", … in the button text. */
  ownerNoun: string;
  onChanged: () => Promise<unknown>;
  /** Id of the element to focus after removing. */
  focusAfter: string;
  /** Called with a sentence for a live region after removing. */
  onDone?: (message: string) => void;
  /** Extra words in the question, e.g. why the project needs another QR before publishing. */
  note?: string;
}

export function DetachButton({
  linkId,
  title,
  ownerNoun,
  onChanged,
  focusAfter,
  onDone,
  note,
}: DetachButtonProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await call(
        api.DELETE("/api/v1/admin/media-links/{id}", { params: { path: { id: linkId } } }),
      );
    } catch (err) {
      setError(problemMessage(err, `Couldn't remove ${title}.`));
      setBusy(false);
      return;
    }
    await onChanged().catch(() => undefined);
    setBusy(false);
    setOpen(false);
    onDone?.(`${title} was removed from this ${ownerNoun}. It stays in the media library.`);
    requestAnimationFrame(() => document.getElementById(focusAfter)?.focus());
  }

  return (
    <>
      <Button
        variant="danger"
        aria-label={`Remove from ${ownerNoun}: ${title}`}
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
      >
        Remove
      </Button>
      <ConfirmDialog
        open={open}
        title={`Remove ${title} from this ${ownerNoun}?`}
        confirmLabel={`Remove from ${ownerNoun}`}
        tone="danger"
        busy={busy}
        error={error}
        onCancel={() => setOpen(false)}
        onConfirm={() => void confirm()}
      >
        It stops showing on the website straight away. The file stays in the media library.
        {note ? ` ${note}` : null}
      </ConfirmDialog>
    </>
  );
}

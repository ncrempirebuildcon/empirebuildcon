"use client";
/**
 * Warns before leaving a screen with unsaved changes (spec: "keep it simple: a warning on leave").
 *
 * How it works:
 *   1. Closing the tab, reloading or typing a new address: the browser's own "Leave site?"
 *      prompt, through `beforeunload` (browsers ignore custom text there).
 *   2. Clicking a link inside the CMS: the click is held and our ConfirmDialog asks
 *      "Leave without saving?"; "Leave" continues to the link. Downloads and blob:, mailto: and
 *      tel: links pass through: they don't leave the page.
 *   3. Sign out (a button, not a link): the shell is told through `setUnsaved` and asks too.
 *   4. A screen that moves on by itself (e.g. "Mark unread" back to the inbox, or picking another
 *      visit on the calendar) calls `leave(href)`: with changes it asks the same question first;
 *      "Stay on this page" keeps the user, and their typing, where they are.
 *   Other buttons that navigate on their own (e.g. Duplicate) are disabled while there are changes.
 *   The browser's Back button is not intercepted: Next.js has no supported way to block it, and
 *   faking one breaks history. `beforeunload` still covers leaving the CMS entirely.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@empire/ui";
import { useAdminSession } from "@/app/admin/session-context";

export function useUnsavedChanges(dirty: boolean) {
  const router = useRouter();
  const { setUnsaved } = useAdminSession();
  const [pending, setPending] = useState<{ href: string; replace: boolean } | null>(null);

  useEffect(() => {
    setUnsaved(dirty);
    return () => setUnsaved(false);
  }, [dirty, setUnsaved]);

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element | null)?.closest?.("a[href]");
      if (!(anchor instanceof HTMLAnchorElement) || anchor.target === "_blank") return;
      // WHY: a download (`<a download>`, e.g. recovery codes as a text file) and blob:, mailto:
      // or tel: links don't leave the page, so nothing typed is lost.
      if (anchor.hasAttribute("download")) return;
      const url = new URL(anchor.href, window.location.href);
      if (url.protocol !== "http:" && url.protocol !== "https:") return;
      if (url.origin !== window.location.origin) return;
      // Same page (e.g. "#main" skip link): nothing is lost.
      if (url.pathname === window.location.pathname && url.search === window.location.search)
        return;
      event.preventDefault();
      event.stopPropagation();
      setPending({ href: url.pathname + url.search + url.hash, replace: false });
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    // WHY capture phase: runs before Next.js <Link> starts its client-side navigation.
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);

  const go = useCallback(
    (href: string, replace: boolean) =>
      replace ? router.replace(href, { scroll: false }) : router.push(href),
    [router],
  );

  /**
   * Go to `href` from code (not a link click): straight away when nothing is unsaved, else after
   * the "Leave without saving?" question. `replace` swaps the current history entry, for a change
   * of view within the same screen.
   */
  const leave = useCallback(
    (href: string, options: { replace?: boolean } = {}) => {
      const replace = options.replace ?? false;
      if (dirty) setPending({ href, replace });
      else go(href, replace);
    },
    [dirty, go],
  );

  const dialog = (
    <ConfirmDialog
      open={pending !== null}
      title="Leave without saving?"
      confirmLabel="Leave without saving"
      cancelLabel="Stay on this page"
      tone="danger"
      onCancel={() => setPending(null)}
      onConfirm={() => {
        const target = pending;
        setPending(null);
        if (target) go(target.href, target.replace);
      }}
    >
      You have changes that are not saved yet. If you leave now, they are lost.
    </ConfirmDialog>
  );

  return { dialog, leave };
}

/**
 * Unsaved changes from several parts of one screen (e.g. the lead page's note, details and visit
 * forms), combined into the one flag `useUnsavedChanges` needs. WHY: the guard must exist once
 * per screen; two guards would fight over the shell's sign-out warning and both ask on leave.
 */
export function useDirtyParts() {
  const [parts, setParts] = useState<Record<string, boolean>>({});
  const report = useCallback(
    (part: string, dirty: boolean) =>
      setParts((current) => (current[part] === dirty ? current : { ...current, [part]: dirty })),
    [],
  );
  return { dirty: Object.values(parts).some(Boolean), report };
}

/** Tells the screen (`onDirtyChange`) whether this part has unsaved changes; clears on unmount. */
export function useReportDirty(
  onDirtyChange: ((dirty: boolean) => void) | undefined,
  dirty: boolean,
) {
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [onDirtyChange, dirty]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
}

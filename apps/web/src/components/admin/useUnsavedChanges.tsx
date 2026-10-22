"use client";
/**
 * Warns before leaving a screen with unsaved changes (spec: "keep it simple: a warning on leave").
 *
 * How it works:
 *   1. Closing the tab, reloading or typing a new address: the browser's own "Leave site?"
 *      prompt, through `beforeunload` (browsers ignore custom text there).
 *   2. Clicking a link inside the CMS: the click is held and our ConfirmDialog asks
 *      "Leave without saving?"; "Leave" continues to the link.
 *   3. Sign out (a button, not a link): the shell is told through `setUnsaved` and asks too.
 *   Buttons that navigate on their own (e.g. Duplicate) are disabled while there are changes.
 *   The browser's Back button is not intercepted: Next.js has no supported way to block it, and
 *   faking one breaks history. `beforeunload` still covers leaving the CMS entirely.
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@empire/ui";
import { useAdminSession } from "@/app/admin/session-context";

export function useUnsavedChanges(dirty: boolean) {
  const router = useRouter();
  const { setUnsaved } = useAdminSession();
  const [pendingHref, setPendingHref] = useState<string | null>(null);

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
      const url = new URL(anchor.href, window.location.href);
      if (url.origin !== window.location.origin) return;
      // Same page (e.g. "#main" skip link): nothing is lost.
      if (url.pathname === window.location.pathname && url.search === window.location.search)
        return;
      event.preventDefault();
      event.stopPropagation();
      setPendingHref(url.pathname + url.search + url.hash);
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    // WHY capture phase: runs before Next.js <Link> starts its client-side navigation.
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);

  const dialog = (
    <ConfirmDialog
      open={pendingHref !== null}
      title="Leave without saving?"
      confirmLabel="Leave without saving"
      cancelLabel="Stay on this page"
      tone="danger"
      onCancel={() => setPendingHref(null)}
      onConfirm={() => {
        const href = pendingHref;
        setPendingHref(null);
        if (href) router.push(href);
      }}
    >
      You have changes that are not saved yet. If you leave now, they are lost.
    </ConfirmDialog>
  );

  return { dialog };
}

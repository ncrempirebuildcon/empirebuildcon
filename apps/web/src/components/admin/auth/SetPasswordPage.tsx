"use client";
/**
 * Loads SetPasswordForm in the browser only.
 * WHY `ssr: false`: the form reads the one-time token from the address when it first renders,
 * which only the browser can do; rendering it on the server too would show a different first
 * screen and make React redo it. It also keeps the token out of any server-rendered HTML.
 */
import dynamic from "next/dynamic";
import type { DoneKind } from "@/lib/auth/links";

const SetPasswordForm = dynamic(
  () => import("./SetPasswordForm").then((module) => module.SetPasswordForm),
  {
    ssr: false,
    loading: () => (
      <p role="status" className="text-small text-muted">
        Checking your link…
      </p>
    ),
  },
);

export function SetPasswordPage({ purpose }: { purpose: DoneKind }) {
  return <SetPasswordForm purpose={purpose} />;
}

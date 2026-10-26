/**
 * /admin/settings (board NoirCmsSettings): company details, RERA, contacts, lead routing,
 * tracking, email and integrations, SEO defaults, privacy, consent texts and feature flags.
 * Needs `settings.read`; each section's Save needs its own permission, which the API checks again.
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import { Alert } from "@empire/ui";
import { requireSessionUser } from "@/lib/session";
import { LoadingPanel } from "@/components/admin/states";
import { AdminShell } from "../AdminShell";
import { SettingsScreen } from "./SettingsScreen";

export const metadata: Metadata = { title: "Settings" };
export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const me = await requireSessionUser();
  const allowed = (me.permissions ?? []).includes("settings.read");
  return (
    <AdminShell me={me} section="settings" heading="Settings">
      {allowed ? (
        // WHY Suspense: the open section lives in the address (`?tab=`).
        <Suspense fallback={<LoadingPanel label="Loading settings…" rows={8} />}>
          <SettingsScreen />
        </Suspense>
      ) : (
        <Alert tone="info">
          Your role can&apos;t open Settings. Ask an admin if something needs changing.
        </Alert>
      )}
    </AdminShell>
  );
}

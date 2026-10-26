/**
 * /admin/reset#token=… (or ?token=… from older emails): choose a new password from a reset email (users/service.py
 * `reset_link`). Signed-out page.
 *
 * SECURITY (SECURITY.md §1): `Referrer-Policy: no-referrer` (here and in next.config.ts), no
 * third-party resources; the token is in the fragment, so it never reaches the server, and it
 * leaves the address bar on load wherever it was (SetPasswordForm.tsx).
 */
import type { Metadata } from "next";
import { AuthCard } from "@/components/admin/auth/AuthCard";
import { SetPasswordPage } from "@/components/admin/auth/SetPasswordPage";

export const metadata: Metadata = { title: "Choose a new password", referrer: "no-referrer" };

export default function ResetPage() {
  return (
    <AuthCard
      eyebrow="EMPIRE CMS"
      title="Choose a new password"
      intro="Choose a new password for your Empire CMS account."
    >
      <SetPasswordPage purpose="reset" />
    </AuthCard>
  );
}

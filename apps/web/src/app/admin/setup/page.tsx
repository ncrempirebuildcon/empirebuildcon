/**
 * /admin/setup#token=… (or ?token=… from older emails): a new staff member chooses their first password from the invite email
 * (users/service.py `setup_link`). Signed-out page.
 *
 * SECURITY (SECURITY.md §1): `Referrer-Policy: no-referrer` (here and in next.config.ts), no
 * third-party resources; the token is in the fragment, so it never reaches the server, and it
 * leaves the address bar on load wherever it was (SetPasswordForm.tsx).
 */
import type { Metadata } from "next";
import { AuthCard } from "@/components/admin/auth/AuthCard";
import { SetPasswordPage } from "@/components/admin/auth/SetPasswordPage";

export const metadata: Metadata = { title: "Set up your account", referrer: "no-referrer" };

export default function SetupPage() {
  return (
    <AuthCard
      eyebrow="EMPIRE CMS"
      title="Set up your account"
      intro="Choose the password you'll use to sign in to the Empire CMS."
    >
      <SetPasswordPage purpose="setup" />
    </AuthCard>
  );
}

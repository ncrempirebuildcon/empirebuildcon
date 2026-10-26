/**
 * /admin/forgot: ask for a password reset link (board NoirCmsLogin's "Forgot password?" link).
 * Signed-out page; the API emails the link (`POST /auth/password/forgot`).
 */
import type { Metadata } from "next";
import { AuthCard } from "@/components/admin/auth/AuthCard";
import { ForgotForm } from "./ForgotForm";

export const metadata: Metadata = { title: "Reset your password" };

export default function ForgotPage() {
  return (
    <AuthCard
      eyebrow="EMPIRE CMS"
      title="Reset your password"
      intro="Enter your work email. If it belongs to a staff account, we'll email a link to choose a new password."
    >
      <ForgotForm />
    </AuthCard>
  );
}

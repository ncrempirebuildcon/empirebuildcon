/**
 * Staff sign-in page (design canvas board "NoirCmsLogin"): email and password, then, for
 * accounts with two-factor, the code step or the forced set-up (LoginForm.tsx draws the card,
 * because each step has its own heading).
 *
 * `?done=setup|reset` shows a confirmation after a setup or reset link was used. It carries no
 * secret; unknown values are ignored.
 */
import type { Metadata } from "next";
import { doneKind } from "@/lib/auth/links";
import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Staff sign-in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return <LoginForm done={doneKind((await searchParams).done)} />;
}

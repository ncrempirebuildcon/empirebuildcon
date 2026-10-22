/**
 * Staff sign-in page (design canvas board "NoirCmsLogin").
 * TODO(phase-4): two-factor step (TOTP) for admin and super-admin accounts behind flag `admin_2fa`
 * (handbook/SECURITY.md §1), and the forgot-password screen.
 */
import Image from "next/image";
import type { Metadata } from "next";
import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Staff sign-in" };

export default function LoginPage() {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="flex w-full max-w-md flex-col items-center gap-6">
        <Image
          src="/brand/logo-stacked-noir.svg"
          alt="Empire — Delivering Happiness"
          width={180}
          height={140}
          priority
          unoptimized
          className="h-auto w-[180px]"
        />
        <section
          aria-labelledby="login-title"
          className="w-full rounded-card-lg border border-gold-line-strong bg-noir-800 p-6 sm:p-8"
        >
          <h1 id="login-title" className="mb-1 text-[26px] font-bold">
            Staff sign-in
          </h1>
          <p className="mb-6 text-small text-muted">Empire CMS · for Empire staff only</p>
          <LoginForm />
        </section>
        <p className="text-caption text-muted">
          No public sign-up. Ask a super-admin for an account.
        </p>
      </div>
    </main>
  );
}

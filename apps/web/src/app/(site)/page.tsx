/**
 * Home: the CMS's "home" page and its blocks (task 5.5a, D-045). Until that page is published
 * the holding content below stays, so the site never shows an empty home page.
 * Restyled with the approved Black & gold theme (D-033, D-038).
 */
import Image from "next/image";
import { PageView } from "@/components/blocks/PageView";
import { fetchPublicPageOrNull } from "@/lib/public/api";

export default async function HomePage() {
  const page = await fetchPublicPageOrNull("home");
  if (page && page.blocks.length > 0) return <PageView page={page} path="/" />;
  return <HoldingPage />;
}

function HoldingPage() {
  return (
    <section className="grid min-h-[60vh] place-items-center px-4 py-16">
      <div className="flex max-w-xl flex-col items-center gap-5 text-center">
        <Image
          src="/brand/logo-stacked-noir.svg"
          alt="Empire — Delivering Happiness"
          width={320}
          height={250}
          priority
          unoptimized
          className="h-auto w-[min(320px,80vw)]"
        />
        <h1 className="font-display text-[clamp(26px,5vw,38px)] leading-tight font-semibold tracking-wide text-metallic">
          Our new website is on its way
        </h1>
        <div className="star-rule w-56 text-xs" aria-hidden="true">
          ✦
        </div>
        <p className="text-lede text-body">
          We&apos;re building a home online for Empire&apos;s projects. Please check back soon.
        </p>
        <p className="text-caption text-muted">empirebuildcon.com</p>
      </div>
    </section>
  );
}

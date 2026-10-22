/**
 * Home: the "coming soon" holding page in Black & gold until the public site ships (Phase 5).
 * Same message as /holding-page (used for the domain check), restyled with the approved theme.
 */
import Image from "next/image";

export default function HomePage() {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-12">
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
    </main>
  );
}

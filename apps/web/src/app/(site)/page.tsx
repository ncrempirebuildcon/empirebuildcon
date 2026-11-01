/**
 * Home: holding content inside the new public shell until 5.5 builds the full home page.
 * Restyled with the approved Black & gold theme (D-033, D-038).
 */
import Image from "next/image";

export default function HomePage() {
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

/**
 * Public website footer: on-brand, accessible and regulatory-compliant.
 *
 * Implements ARCHITECTURE §15, DESIGN_SYSTEM & D-038:
 *   - Displays company details, addresses, phones and emails from CMS settings.
 *   - Placeholders in [brackets] are hidden in production.
 *   - Regulatory line for UP-RERA with up-rera.in link.
 *   - Equal-weight WhatsApp contact and dialable phones.
 *   - © current year Empire and legal links (Privacy, Terms, Disclaimer).
 */
import Image from "next/image";
import Link from "next/link";
import {
  buildTelLink,
  buildWhatsAppLink,
  filterPlaceholders,
  filterValue,
} from "@/lib/public/format";
import type { PublicSite } from "@/lib/public/api";

export function Footer({ site, isProduction }: { site?: PublicSite; isProduction?: boolean }) {
  const currentYear = new Date().getFullYear();
  const company = site?.company;
  const regulator = site?.regulator;

  const phones = filterPlaceholders(company?.phones ?? [], isProduction);
  const emails = filterPlaceholders(company?.emails ?? [], isProduction);
  const registeredAddress = filterValue(company?.registered_address, isProduction);
  const corporateAddress = filterValue(company?.corporate_address, isProduction);
  const address = filterValue(company?.address, isProduction);
  const officeHours = filterValue(company?.office_hours, isProduction);

  const primaryPhone = phones[0];
  const whatsappHref = buildWhatsAppLink(
    company?.whatsapp || primaryPhone,
    company?.whatsapp_message,
    "/",
    isProduction,
  );

  const displayAddresses = [registeredAddress, corporateAddress, address].filter(
    (a, i, arr): a is string => Boolean(a && arr.indexOf(a) === i),
  );

  return (
    <footer
      role="contentinfo"
      className="border-t border-gold-500/35 bg-noir-950 text-sand-300"
      data-testid="public-footer"
    >
      <div className="mx-auto flex max-w-7xl flex-col gap-9 px-4 py-12 md:px-8 md:py-16">
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4 items-start">
          {/* Brand Mark & Tagline */}
          <div className="flex flex-col gap-4">
            <Link href="/" aria-label="Empire home" className="inline-block">
              <Image
                src="/brand/logo-stacked-noir.svg"
                alt={
                  company?.name
                    ? `${company.name} — Delivering Happiness`
                    : "Empire — Delivering Happiness"
                }
                width={160}
                height={120}
                unoptimized
                className="h-20 w-auto"
              />
            </Link>
            {company?.tagline && <p className="text-xs text-sand-400 italic">{company.tagline}</p>}
            {company?.legal_name && <p className="text-xs text-sand-400">{company.legal_name}</p>}
            {company?.gstin && <p className="text-xs text-sand-400">GSTIN: {company.gstin}</p>}
          </div>

          {/* Navigation - Projects */}
          <nav aria-label="Projects" className="flex flex-col gap-2.5 text-sm">
            <strong className="font-display text-xs font-semibold tracking-wider text-gold-400">
              PROJECTS
            </strong>
            <Link href="/projects" className="hover:text-gold-300">
              All projects
            </Link>
            <Link href="/projects?status=ongoing" className="hover:text-gold-300">
              Ongoing projects
            </Link>
            <Link href="/projects?status=completed" className="hover:text-gold-300">
              Completed projects
            </Link>
            <Link href="/properties" className="hover:text-gold-300">
              Properties by BHK
            </Link>
          </nav>

          {/* Navigation - Company */}
          <nav aria-label="Company" className="flex flex-col gap-2.5 text-sm">
            <strong className="font-display text-xs font-semibold tracking-wider text-gold-400">
              COMPANY
            </strong>
            <Link href="/about" className="hover:text-gold-300">
              About Empire
            </Link>
            <Link href="/contact" className="hover:text-gold-300">
              Contact us
            </Link>
            <Link href="/contact#visit" className="hover:text-gold-300">
              Book a site visit
            </Link>
            <Link href="/blog" className="hover:text-gold-300">
              News & updates
            </Link>
          </nav>

          {/* Contact Details */}
          <div className="flex flex-col gap-2.5 text-sm">
            <strong className="font-display text-xs font-semibold tracking-wider text-gold-400">
              CONTACT
            </strong>
            {displayAddresses.map((addr) => (
              <address key={addr} className="not-italic text-xs text-sand-300 leading-relaxed">
                {addr}
              </address>
            ))}
            {officeHours && <span className="text-xs text-sand-400">Hours: {officeHours}</span>}
            {phones.map((phone) => {
              const tel = buildTelLink(phone, isProduction);
              return tel ? (
                <a key={phone} href={tel} className="hover:text-gold-300">
                  {phone}
                </a>
              ) : null;
            })}
            {emails.map((email) => (
              <a key={email} href={`mailto:${email}`} className="hover:text-gold-300">
                {email}
              </a>
            ))}
            {whatsappHref && (
              <a
                href={whatsappHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-palm-300 hover:text-palm-200 font-semibold"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path d="M4 20l1.3-3.9A8 8 0 1 1 8 19.3L4 20z" />
                </svg>
                WhatsApp us
              </a>
            )}
          </div>
        </div>

        {/* Official Channels Note */}
        <p className="border-t border-noir-800 pt-5 text-xs text-gold-300/90 leading-relaxed">
          Official channels: empirebuildcon.com
          {primaryPhone ? ` and ${primaryPhone}` : ""} only. Empire never asks for payments to
          personal accounts.
        </p>

        {/* UP-RERA Regulator Note */}
        <p className="text-xs text-sand-400 leading-relaxed">
          Every project on this site shows its {regulator?.authority ?? "UP-RERA"} registration
          number and QR code on its project page; verify at{" "}
          <a
            href={regulator?.website ?? "https://up-rera.in"}
            target="_blank"
            rel="noopener noreferrer"
            className="text-gold-400 underline hover:text-gold-300"
          >
            {regulator?.website?.replace(/^https?:\/\//, "") ?? "up-rera.in"}
          </a>
          . Images are artist&apos;s impressions. Prices exclude GST, stamp duty and registration
          unless stated. Nothing on this site is an offer or a promise of returns.
        </p>

        {/* Bottom Bar: Copyright & Legal */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-noir-800 pt-5 text-xs text-sand-400">
          <span>© {currentYear} Empire</span>
          <div className="flex flex-wrap gap-4 sm:gap-6">
            <Link href="/privacy" className="hover:text-sand-200">
              Privacy policy
            </Link>
            <Link href="/terms" className="hover:text-sand-200">
              Terms
            </Link>
            <Link href="/disclaimer" className="hover:text-sand-200">
              Disclaimer
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}

export default Footer;

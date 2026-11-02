/**
 * Public website footer (Phase 5 Task 5.2, S8).
 *
 * Implements ARCHITECTURE §15, DESIGN_SYSTEM, D-038 & D-039:
 *   - Official channels notice (empirebuildcon.com and phone only).
 *   - Mandatory UP-RERA regulator line and up-rera.in verification link.
 *   - Social links from site settings (S8).
 *   - Current page path in WhatsApp link via FooterWhatsApp (S8).
 *   - WhatsApp falls back to phone number if whatsapp field is placeholder/missing (S8).
 *   - Placeholders hidden in production.
 *   - Legal links (Privacy, Terms, Disclaimer) and copyright year.
 */
import Link from "next/link";
import type { PublicSite } from "@/lib/public/api";
import { buildTelLink, filterPlaceholders, filterValue } from "@/lib/public/format";
import FooterWhatsApp from "./FooterWhatsApp";

export function Footer({
  site,
  isProduction = false,
}: {
  site?: PublicSite;
  isProduction?: boolean;
}) {
  const company = site?.company;
  const regulator = site?.regulator;
  const social = site?.social || {};

  const currentYear = new Date().getFullYear();

  const primaryPhone = company?.phones?.[0] ? filterValue(company.phones[0], isProduction) : null;

  const rawWhatsApp = company?.whatsapp ? filterValue(company.whatsapp, isProduction) : null;
  // S8: If whatsapp is placeholder/empty, fall back to the phone number
  const effectiveWhatsApp = rawWhatsApp || primaryPhone;

  const phones = filterPlaceholders(company?.phones ?? [], isProduction);
  const emails = filterPlaceholders(company?.emails ?? [], isProduction);
  const registeredAddress = filterValue(company?.registered_address, isProduction);
  const corporateAddress = filterValue(company?.corporate_address, isProduction);
  const address = filterValue(company?.address, isProduction);
  const displayAddresses = [registeredAddress, corporateAddress, address].filter(
    (a, i, arr): a is string => Boolean(a && arr.indexOf(a) === i),
  );
  const officeHours = filterValue(company?.office_hours, isProduction);

  // Filter social links (drop placeholders/empty)
  const socialEntries = Object.entries(social)
    .map(([platform, url]) => [platform, filterValue(url, isProduction)] as const)
    .filter((entry): entry is [string, string] => Boolean(entry[1]));

  return (
    <footer
      role="contentinfo"
      className="border-t border-gold-500/40 bg-noir-900 text-sand-300"
      data-testid="public-footer"
    >
      <div className="mx-auto flex max-w-7xl flex-col gap-10 px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-4">
          {/* Brand & Mission */}
          <div className="flex flex-col gap-3 md:col-span-1">
            <Link
              href="/"
              className="font-display text-xl font-bold tracking-[0.16em] text-sand-100 uppercase hover:text-gold-300"
            >
              EMPIRE
            </Link>
            {company?.tagline && (
              <p className="text-xs text-sand-400 leading-relaxed">{company.tagline}</p>
            )}
            {company?.legal_name && (
              <p className="text-[11px] text-sand-400/80">{company.legal_name}</p>
            )}
            {company?.gstin && (
              <p className="text-[11px] text-sand-400/80">GSTIN: {company.gstin}</p>
            )}

            {/* Social links (S8) */}
            {socialEntries.length > 0 && (
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <span className="sr-only">Social media links</span>
                {socialEntries.map(([platform, url]) => (
                  <a
                    key={platform}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex h-11 w-11 min-h-[44px] min-w-[44px] items-center justify-center rounded-full border border-gold-500/30 text-xs font-semibold text-gold-400 hover:border-gold-400 hover:text-gold-300 capitalize"
                    aria-label={`Follow Empire on ${platform}`}
                  >
                    {platform.slice(0, 2).toUpperCase()}
                  </a>
                ))}
              </div>
            )}
          </div>

          {/* Navigation - Explore */}
          <nav aria-label="Explore" className="flex flex-col gap-2.5 text-sm">
            <strong className="font-display text-xs font-semibold tracking-wider text-gold-400">
              EXPLORE
            </strong>
            <Link href="/projects" className="hover:text-gold-300">
              All projects
            </Link>
            <Link href="/properties" className="hover:text-gold-300">
              Properties
            </Link>
            <Link href="/projects?city=lucknow" className="hover:text-gold-300">
              Lucknow projects
            </Link>
            <Link href="/projects?city=noida" className="hover:text-gold-300">
              Noida projects
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
            <FooterWhatsApp
              phone={effectiveWhatsApp}
              template={company?.whatsapp_message}
              isProduction={isProduction}
            />
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

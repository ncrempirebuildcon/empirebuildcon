/**
 * /contact: how to reach Empire, the site-visit form and an enquiry form (board NoirContact;
 * task 5.4, D-043).
 *
 * WHY a code route: it is the target of every "Enquire" and "Book a site visit" link and needs
 * the forms; the CMS's "contact" system page adds its blocks in 5.5a. Contact details come from
 * site settings, with placeholders hidden in production (D-038), never invented.
 *
 * `?project=<slug>` preselects that project in both forms (links from project and property
 * pages); an unknown slug is ignored.
 */
import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/catalogue/ListControls";
import { LeadPanel } from "@/components/leads/LeadPanel";
import { fetchPublicProjects, fetchPublicSite } from "@/lib/public/api";
import {
  buildTelLink,
  buildWhatsAppLink,
  filterPlaceholders,
  filterValue,
  isProductionEnv,
} from "@/lib/public/format";
import type { SearchParams } from "@/lib/public/catalogue";

export const metadata: Metadata = { title: "Contact" };

export default async function ContactPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const [site, projects] = await Promise.all([
    fetchPublicSite(),
    fetchPublicProjects({ per_page: 100, page: 1 }),
  ]);
  const prod = isProductionEnv();
  const company = site.company;
  const choices = projects.items
    .filter((p) => p.sales_status !== "sold_out")
    .map((p) => ({
      slug: p.slug,
      name: p.locality ? `${p.name} · ${p.locality.name}` : p.name,
    }));
  const wanted = typeof params.project === "string" ? params.project : undefined;
  const preselect = choices.some((c) => c.slug === wanted) ? wanted : undefined;

  const phones = filterPlaceholders(company?.phones ?? [], prod);
  const emails = filterPlaceholders(company?.emails ?? [], prod);
  const hours = filterValue(company?.office_hours, prod);
  const whatsapp = filterValue(company?.whatsapp, prod) ?? phones[0] ?? null;
  const wa = buildWhatsAppLink(whatsapp, company?.whatsapp_message, "/contact", prod);
  const addresses = [
    filterValue(company?.address, prod),
    filterValue(company?.corporate_address, prod),
    filterValue(company?.registered_address, prod),
  ].filter((a, i, all): a is string => Boolean(a) && all.indexOf(a) === i);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-10 px-4 py-10 sm:px-6 lg:px-8">
      <Breadcrumbs items={[{ href: "/", label: "Home" }, { label: "Contact" }]} />
      <header className="flex flex-col gap-3">
        <p className="font-display text-eyebrow tracking-[0.28em] text-gold-400 uppercase">
          Contact
        </p>
        <h1 className="font-display text-[clamp(32px,6vw,58px)] leading-tight font-semibold text-balance text-metallic">
          Talk to Empire
        </h1>
        <p className="max-w-[42em] text-lede text-body">
          Call, message or visit. A real person answers during office hours.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <section aria-labelledby="reach-title" className="flex flex-col gap-4">
          <h2 id="reach-title" className="font-display text-h2-mobile font-semibold sm:text-h2">
            Reach us
          </h2>
          {phones.length > 0 ? (
            <ul className="flex flex-col gap-1" aria-label="Phone numbers">
              {phones.map((p) => (
                <li key={p}>
                  <a
                    href={buildTelLink(p, prod) ?? undefined}
                    className="inline-flex min-h-11 items-center font-semibold tabular-nums"
                  >
                    {p}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
          {wa ? (
            <a
              href={wa}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center self-start rounded-pill bg-palm-bg px-5 font-semibold text-palm"
            >
              WhatsApp us<span className="sr-only"> (opens in a new tab)</span>
            </a>
          ) : null}
          {emails.length > 0 ? (
            <ul className="flex flex-col gap-1" aria-label="Email addresses">
              {emails.map((e) => (
                <li key={e}>
                  <a href={`mailto:${e}`} className="inline-flex min-h-11 items-center">
                    {e}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
          {hours ? <p className="text-small text-muted">Office hours: {hours}</p> : null}
          {addresses.map((a) => (
            <address key={a} className="text-body not-italic">
              {a}
            </address>
          ))}
          {phones.length === 0 && emails.length === 0 && !wa ? (
            <p className="text-body">Our contact numbers will be listed here soon.</p>
          ) : null}
          <div className="rounded-tile border border-line bg-noir-800 p-4 text-small text-body">
            <p className="font-semibold text-ivory">Official channels only</p>
            <p>
              Empire&apos;s only website is empirebuildcon.com. Pay only into each project&apos;s
              RERA designated account. Empire never asks for payment into a personal account.
            </p>
          </div>
        </section>

        <section
          id="visit"
          className="scroll-mt-24 rounded-card border border-gold-line-strong bg-noir-800 p-5"
        >
          <LeadPanel
            intent="visit"
            title="Book a site visit"
            intro="Pick a project, a day and a time of day. We confirm the exact time by phone."
            submitLabel="Request a site visit"
            path="/contact"
            projectSlug={preselect}
            projectChoices={choices}
          />
        </section>
      </div>

      <section
        id="enquire"
        className="scroll-mt-24 rounded-card border border-gold-line bg-noir-800 p-5 lg:max-w-2xl"
      >
        <LeadPanel
          intent="enquiry"
          title="Send us a question"
          submitLabel="Send"
          path="/contact"
          projectSlug={preselect}
          projectChoices={choices}
        />
      </section>
    </div>
  );
}

/**
 * Server wrapper for the lead forms (task 5.4, D-043): reads the current consent texts and the
 * contact numbers from /public/site (cached by the `site` tag) and renders `LeadForm`, with an
 * honest "call or WhatsApp" fallback for no JavaScript or no current consent text.
 *
 * Placeholders (`[…]`) are hidden in production (D-038), so the fallback never shows a made-up
 * number; with no number at all it points to the contact page.
 */
import Link from "next/link";
import { fetchPublicSite } from "@/lib/public/api";
import { buildTelLink, buildWhatsAppLink, filterValue, isProductionEnv } from "@/lib/public/format";
import type { LeadIntent } from "@/lib/public/leads";
import { LeadForm, type ConsentText } from "./LeadForm";

export interface LeadPanelProps {
  intent: LeadIntent;
  title: string;
  intro?: string;
  submitLabel: string;
  /** The path this panel is on, for the WhatsApp message's `{page}`. */
  path: string;
  projectSlug?: string | null;
  configurationId?: string | null;
  projectChoices?: { slug: string; name: string }[];
  headingLevel?: 2 | 3;
}

export async function LeadPanel(props: LeadPanelProps) {
  const site = await fetchPublicSite();
  const prod = isProductionEnv();
  const consent = (site.consent?.lead_form ?? null) as ConsentText | null;
  const marketing = (site.consent?.marketing ?? null) as ConsentText | null;
  const phone = site.company?.phones?.[0] ? filterValue(site.company.phones[0], prod) : null;
  const whatsapp =
    (site.company?.whatsapp ? filterValue(site.company.whatsapp, prod) : null) ?? phone;
  const tel = buildTelLink(phone, prod);
  const wa = buildWhatsAppLink(whatsapp, site.company?.whatsapp_message, props.path, prod);

  const fallback = (
    <div className="flex flex-col gap-2 text-small text-body" data-testid="lead-fallback">
      <p>
        {consent
          ? "This form needs JavaScript. You can also reach our sales team directly:"
          : "Enquiries from the website open soon. Meanwhile, please reach our sales team directly:"}
      </p>
      <div className="flex flex-wrap gap-3">
        {tel ? (
          <a href={tel} className="inline-flex min-h-11 items-center font-semibold">
            Call sales
          </a>
        ) : null}
        {wa ? (
          <a
            href={wa}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center font-semibold text-palm"
          >
            WhatsApp<span className="sr-only"> (opens in a new tab)</span>
          </a>
        ) : null}
        {!tel && !wa ? (
          <Link href="/contact" className="inline-flex min-h-11 items-center font-semibold">
            Contact details
          </Link>
        ) : null}
      </div>
    </div>
  );

  return (
    <LeadForm
      intent={props.intent}
      title={props.title}
      intro={props.intro}
      submitLabel={props.submitLabel}
      consent={consent}
      marketing={marketing}
      projectSlug={props.projectSlug}
      configurationId={props.configurationId}
      projectChoices={props.projectChoices}
      headingLevel={props.headingLevel}
      fallback={fallback}
    />
  );
}

export default LeadPanel;

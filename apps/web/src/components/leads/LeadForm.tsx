"use client";

/**
 * Public lead form: an enquiry, a site-visit request or a gated brochure (task 5.4, D-043;
 * boards NoirProject, NoirProperty, NoirContact; DESIGN_SYSTEM §8 "Lead form").
 *
 * How it works:
 *   1. The server page passes the current consent texts from /public/site. With no current
 *      lead-form text the form isn't drawn; an honest "call or WhatsApp" note is shown instead.
 *   2. The form is in the page's HTML from the start, switched off (a disabled fieldset) until
 *      React has hydrated it: it posts with fetch, so it needs JavaScript. With JavaScript off
 *      it stays off, and the "call or WhatsApp" note shows above it (`<noscript>`).
 *      PERF (task 5.7c, D-049, owner's decision 5 Nov 2026): drawing the whole form only after
 *      hydration made a long task, a late LCP on /contact, and a "needs JavaScript" flash on
 *      slow phones.
 *   3. On submit the body is built by lib/public/leads.ts and sent to the site's own /api
 *      proxy, which adds the visitor's network for the API's rate limit (SECURITY §1).
 *   4. The answer becomes a message in a live region; field errors sit under their fields.
 *      Nothing typed is lost on an error.
 *
 * COMPLIANCE (AGENTS.md "Consent", D-017): two separate boxes, never pre-ticked; the required
 * box carries the current text's label and the full text can be opened; marketing consent is
 * sent only when ticked. The honeypot (`website`) is hidden from people and screen readers.
 */
import {
  type FormEvent,
  type ReactNode,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import Link from "next/link";
import { Button, Checkbox, Select, Textarea, TextField } from "@empire/ui";
import {
  captureAttribution,
  checkBeforeSend,
  ENDPOINT,
  leadBody,
  OFFLINE_MESSAGE,
  type Outcome,
  outcomeFor,
  type VisitSlot,
  visitDateRange,
  type LeadInput,
  type LeadIntent,
} from "@/lib/public/leads";

export interface ConsentText {
  id: string;
  version: number;
  body: string;
  checkbox_label: string;
}

export interface LeadFormProps {
  intent: LeadIntent;
  /** Heading of the form (h2 or h3 decided by `headingLevel`). */
  title: string;
  intro?: string;
  consent: ConsentText | null;
  marketing: ConsentText | null;
  projectSlug?: string | null;
  configurationId?: string | null;
  /** A page-builder form's source ("campaign" on landing pages); default from the intent. */
  source?: LeadInput["source"];
  /** On the contact page: the projects a visit can be for, and the one to preselect. */
  projectChoices?: { slug: string; name: string }[];
  /** Shown instead of the form when it can't be used (no JavaScript, no consent text). */
  fallback: ReactNode;
  headingLevel?: 2 | 3;
  submitLabel: string;
}

const SLOTS: { value: VisitSlot; label: string }[] = [
  { value: "morning", label: "Morning (10 am – 1 pm)" },
  { value: "afternoon", label: "Afternoon (1 pm – 4 pm)" },
  { value: "evening", label: "Evening (4 pm – 7 pm)" },
];

function safeSessionStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function noSubscribe(): () => void {
  return () => {};
}

export function LeadForm(props: LeadFormProps) {
  const {
    intent,
    title,
    intro,
    consent,
    marketing,
    projectChoices,
    fallback,
    headingLevel = 2,
    submitLabel,
  } = props;
  const hydrated = useSyncExternalStore(
    noSubscribe,
    () => true,
    () => false,
  );
  const id = useId();
  const statusRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [projectSlug, setProjectSlug] = useState(props.projectSlug ?? "");
  const range = visitDateRange();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const fieldErrors = outcome?.kind === "fields" ? outcome.fields : {};
  // The API field names this form draws (lib/public/leads.ts outcomeFor).
  const shownFields = new Set([
    "name",
    "phone",
    ...(intent === "enquiry" ? ["email", "message"] : []),
    ...(intent === "visit" ? ["preferred_date", "preferred_slot"] : []),
    ...(projectChoices && projectChoices.length > 0 ? ["project_slug"] : []),
  ]);

  if (!consent) {
    // COMPLIANCE: no current lead-form text → no form (the API would refuse it with 503).
    return (
      <section
        aria-labelledby={`${id}-title`}
        className="flex flex-col gap-3"
        data-testid="lead-form-closed"
      >
        <Heading id={`${id}-title`} className="font-display text-h3 font-semibold">
          {title}
        </Heading>
        {fallback}
      </section>
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !consent) return;
    const form = new FormData(event.currentTarget);
    const text = (name: string) => String(form.get(name) ?? "");
    // COMPLIANCE: the required box is checked here, where the body is built, whatever sent the
    // form (button, Enter key, requestSubmit). Without it nothing is sent.
    if (form.get("consent") !== "on") {
      setOutcome({
        kind: "error",
        message: "Please tick the required box so we may contact you about this.",
      });
      requestAnimationFrame(() => statusRef.current?.focus());
      return;
    }
    const before = checkBeforeSend(
      intent,
      {
        name: text("name"),
        phone: text("phone"),
        projectSlug: projectSlug || null,
        preferredDate: text("preferred_date"),
      },
      intent === "visit" && Boolean(projectChoices?.length),
    );
    if (Object.keys(before).length > 0) {
      setOutcome({
        kind: "fields",
        fields: before,
        message: "Please check the highlighted fields.",
      });
      requestAnimationFrame(() => statusRef.current?.focus());
      return;
    }
    setBusy(true);
    setOutcome(null);
    const body = leadBody(
      intent,
      {
        name: text("name"),
        phone: text("phone"),
        email: text("email"),
        message: text("message"),
        projectSlug: projectSlug || null,
        configurationId: props.configurationId ?? null,
        preferredDate: text("preferred_date"),
        preferredSlot: (text("preferred_slot") || "morning") as VisitSlot,
        consent,
        marketing,
        marketingTicked: form.get("marketing") === "on",
        website: text("cf_ref"),
        source: props.source,
      },
      {
        pathname: window.location.pathname,
        referrer: document.referrer,
        attribution: captureAttribution(window.location.search, safeSessionStorage()),
      },
    );
    let next: Outcome;
    try {
      const response = await fetch(ENDPOINT[intent], {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
        credentials: "omit",
      });
      let data: unknown = null;
      try {
        data = await response.json();
      } catch {
        data = null;
      }
      next = outcomeFor(response.status, data, shownFields);
    } catch {
      next = { kind: "error", message: OFFLINE_MESSAGE };
    }
    setOutcome(next);
    setBusy(false);
    // Move focus to the message so keyboard and screen-reader users hear the result.
    requestAnimationFrame(() => statusRef.current?.focus());
  }

  if (outcome?.kind === "ok") {
    return (
      <section aria-labelledby={`${id}-title`} className="flex flex-col gap-3">
        <Heading id={`${id}-title`} className="font-display text-h3 font-semibold">
          {title}
        </Heading>
        <div
          ref={statusRef}
          tabIndex={-1}
          role="status"
          className="flex flex-col gap-2 rounded-tile border border-palm-line bg-palm-bg p-4 text-ivory"
          data-testid="lead-success"
        >
          <p className="font-semibold">{outcome.message}</p>
          <p className="text-small">
            Your reference: <span className="font-bold tabular-nums">{outcome.reference}</span>
          </p>
          {outcome.brochureUrl ? (
            <a
              href={outcome.brochureUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center font-semibold"
              data-testid="brochure-download"
            >
              Download the brochure (PDF)<span className="sr-only"> (opens in a new tab)</span>
            </a>
          ) : null}
        </div>
      </section>
    );
  }

  return (
    <section aria-labelledby={`${id}-title`} className="flex flex-col gap-3">
      <Heading id={`${id}-title`} className="font-display text-h3 font-semibold">
        {title}
      </Heading>
      {intro ? <p className="text-small text-body">{intro}</p> : null}
      {/* WHY only before hydration: React doesn't rebuild <noscript> on the client, so it is
          dropped once the form works; with JavaScript off it is the note visitors read. */}
      {!hydrated ? <noscript>{fallback}</noscript> : null}
      <form
        noValidate
        onSubmit={onSubmit}
        aria-labelledby={`${id}-title`}
        data-testid={`lead-form-${intent}`}
      >
        <fieldset disabled={!hydrated} className="m-0 flex min-w-0 flex-col gap-4 border-0 p-0">
          <TextField
            label="Your name"
            name="name"
            autoComplete="name"
            required
            minLength={2}
            maxLength={80}
            error={fieldErrors.name}
          />
          <TextField
            label="Mobile number"
            name="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel-national"
            required
            maxLength={20}
            hint="Indian mobile or landline. Outside India? Please WhatsApp or email us."
            error={fieldErrors.phone}
          />
          {projectChoices && projectChoices.length > 0 ? (
            <Select
              label={intent === "visit" ? "Project" : "Project (optional)"}
              name="project"
              value={projectSlug}
              onChange={(e) => setProjectSlug(e.target.value)}
              placeholder="Choose a project"
              options={projectChoices.map((p) => ({ value: p.slug, label: p.name }))}
              required={intent === "visit"}
              error={fieldErrors.project_slug}
            />
          ) : null}
          {intent === "visit" ? (
            <>
              <TextField
                label="Preferred day"
                name="preferred_date"
                type="date"
                required
                min={range.min}
                max={range.max}
                defaultValue={range.min}
                hint="We confirm the exact time by phone."
                error={fieldErrors.preferred_date}
              />
              <Select
                label="Time of day"
                name="preferred_slot"
                defaultValue="morning"
                options={SLOTS}
                error={fieldErrors.preferred_slot}
              />
            </>
          ) : null}
          {intent === "enquiry" ? (
            <>
              <TextField
                label="Email (optional)"
                name="email"
                type="email"
                autoComplete="email"
                maxLength={200}
                error={fieldErrors.email}
              />
              <Textarea
                label="Message (optional)"
                name="message"
                maxLength={2000}
                rows={3}
                error={fieldErrors.message}
              />
            </>
          ) : null}

          {/* SECURITY: the honeypot (sent as the API's `website`). Bots fill every field; people
              never see this one, and its name means nothing to browser autofill. */}
          <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
            <label>
              Leave this empty
              <input type="text" name="cf_ref" tabIndex={-1} autoComplete="off" defaultValue="" />
            </label>
          </div>

          <fieldset className="flex flex-col gap-3">
            <legend className="sr-only">Consent</legend>
            <Checkbox
              name="consent"
              required
              label={consent.checkbox_label}
              data-testid="consent-required"
            />
            <details className="text-small text-muted">
              <summary className="inline-flex min-h-11 cursor-pointer items-center">
                Read the full consent text
              </summary>
              <p className="whitespace-pre-line">{consent.body}</p>
            </details>
            {marketing ? (
              <Checkbox
                name="marketing"
                label={
                  <>
                    {marketing.checkbox_label} <span className="text-muted">(Optional)</span>
                  </>
                }
                data-testid="consent-marketing"
              />
            ) : null}
          </fieldset>

          <div
            ref={statusRef}
            tabIndex={-1}
            role="alert"
            className={
              outcome
                ? "rounded-tile border border-danger bg-danger-bg p-3 text-small text-danger-on-bg"
                : "sr-only"
            }
            data-testid="lead-message"
          >
            {outcome ? outcome.message : ""}
            {outcome?.kind === "reload" ? (
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="ml-2 inline-flex min-h-11 items-center font-semibold underline"
              >
                Reload the page
              </button>
            ) : null}
          </div>

          <Button type="submit" loading={busy}>
            {submitLabel}
          </Button>
          <p className="text-caption text-muted">
            <Link href="/privacy" className="underline underline-offset-2">
              Privacy notice
            </Link>{" "}
            · you can withdraw consent any time.
          </p>
        </fieldset>
      </form>
    </section>
  );
}

export default LeadForm;

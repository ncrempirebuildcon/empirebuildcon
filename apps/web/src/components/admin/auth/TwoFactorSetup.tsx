"use client";
/**
 * Setting up two-factor sign-in (board NoirCmsLogin's set-up step; also My account): scan the QR
 * code or type the key into an authenticator app, confirm with the app's 6-digit code, then save
 * the recovery codes (RecoveryCodes.tsx). Used at sign-in, when the `admin_2fa` flag makes it
 * required, and from My account, where it is a choice; only the API calls differ (`start`,
 * `confirm`).
 *
 * Accessibility: the QR image always has the typed key next to it as the alternative, and its
 * alt text says so (WCAG 1.1.1); the code field asks for the numeric keypad and the phone's
 * one-time-code autofill.
 *
 * SECURITY (SECURITY.md §1): the key and the QR are shown only during set-up and held only in
 * memory; once confirmed they are dropped from state, and the API never returns them again.
 * Nothing here is logged, stored in the browser or put in the address.
 */
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Alert, Button, OneTimeCodeField } from "@empire/ui";
import { problemMessage } from "@/lib/problems";
import { RecoveryCodes } from "./RecoveryCodes";

export interface SetupDetails {
  otpauth_uri: string;
  /** The base32 key, grouped for typing ("ABCD EFGH …"). */
  secret: string;
  /** The QR code as an `image/svg+xml` data URL made by the API. */
  qr_svg_data_url: string;
}

type Phase =
  | { name: "starting" }
  | { name: "failed"; message: string }
  | { name: "scan"; details: SetupDetails }
  | { name: "codes"; codes: string[] };

export interface TwoFactorSetupProps {
  email: string;
  /** Starts set-up: a new key from the API. */
  start: () => Promise<SetupDetails>;
  /** Confirms with a code from the app; resolves to the recovery codes, or throws the problem. */
  confirm: (code: string) => Promise<string[]>;
  /** After the recovery codes were saved ("I've saved them" ticked, then the button). */
  onDone: () => void;
  doneLabel: string;
  /** Called once two-factor is on (the code was confirmed), before the codes are shown. */
  onConfirmed?: () => void;
  /**
   * A way out (Back, Cancel) shown only BEFORE two-factor is confirmed. INVARIANT (review L7):
   * while the recovery codes are on screen the only way on is "I've saved them", because they
   * are shown once and two-factor is already on.
   */
  cancel?: ReactNode;
  /** Headings inside this component start at this level (2 on My account, 2 at sign-in). */
  headingLevel?: 2 | 3;
}

/** Only data URLs of SVG images are shown, so a bad answer can't point the image elsewhere. */
export function isSvgDataUrl(value: string): boolean {
  return /^data:image\/svg\+xml(;[a-z0-9=-]+)*[;,]/i.test(value);
}

export function TwoFactorSetup({
  email,
  start,
  confirm,
  onDone,
  doneLabel,
  onConfirmed,
  cancel,
  headingLevel = 2,
}: TwoFactorSetupProps) {
  const [phase, setPhase] = useState<Phase>({ name: "starting" });
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const started = useRef(false);
  const Heading = headingLevel === 2 ? "h2" : "h3";

  useEffect(() => {
    // WHY a ref: React's development double-mount would otherwise start set-up twice, and the
    // second key would replace the first after the person had scanned it.
    if (started.current) return;
    started.current = true;
    start().then(
      (details) => setPhase({ name: "scan", details }),
      (err: unknown) =>
        setPhase({ name: "failed", message: problemMessage(err, "Couldn't start the set-up.") }),
    );
  }, [start]);

  async function onConfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (code.length !== 6) return setError("Enter the 6-digit code from the app.");
    setBusy(true);
    setError(undefined);
    try {
      const codes = await confirm(code);
      setCode("");
      // SECURITY: the key and QR leave memory here; only the recovery codes are shown now.
      setPhase({ name: "codes", codes });
      onConfirmed?.();
    } catch (err) {
      setCode("");
      setError(problemMessage(err, "That code isn't right. Check the app and try again."));
    } finally {
      setBusy(false);
    }
  }

  if (phase.name === "starting") {
    return (
      <div className="flex flex-col gap-4">
        <p role="status" className="text-small text-muted">
          Making your key…
        </p>
        {cancel}
      </div>
    );
  }
  if (phase.name === "failed") {
    return (
      <div className="flex flex-col gap-4">
        <Alert tone="error">{phase.message}</Alert>
        {cancel}
      </div>
    );
  }
  if (phase.name === "codes") {
    return (
      <div className="flex flex-col gap-3">
        <Heading className="text-lg font-bold">Save your recovery codes</Heading>
        <RecoveryCodes codes={phase.codes} email={email} onDone={onDone} doneLabel={doneLabel} />
      </div>
    );
  }

  const { details } = phase;
  return (
    <div className="flex flex-col gap-4">
      <ol className="flex list-decimal flex-col gap-1.5 pl-5 text-small">
        <li>
          Open an authenticator app on your phone (for example Google Authenticator, Microsoft
          Authenticator or 1Password).
        </li>
        <li>Scan the QR code, or type the key below into the app.</li>
        <li>Enter the 6-digit code the app shows.</li>
      </ol>
      <div className="flex flex-wrap items-center gap-4">
        {isSvgDataUrl(details.qr_svg_data_url) ? (
          // WHY a plain <img>: a data URL needs no optimising, and next/image would refuse it.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={details.qr_svg_data_url}
            alt="QR code for your authenticator app. If you can't scan it, type the key shown next to it."
            width={176}
            height={176}
            className="size-44 rounded-tile bg-ivory p-2"
          />
        ) : null}
        <div className="flex min-w-0 flex-[1_1_200px] flex-col gap-1.5">
          <span className="text-small font-semibold text-ivory">Key to type in</span>
          <code className="font-mono text-base tracking-wider [overflow-wrap:anywhere] text-gold-300">
            {details.secret}
          </code>
          <span className="text-caption text-muted">
            Account: {email}. Time-based, 6 digits, every 30 seconds.
          </span>
        </div>
      </div>
      <form
        noValidate
        onSubmit={onConfirm}
        aria-label="Confirm two-factor set-up"
        className="flex flex-col gap-4"
      >
        <OneTimeCodeField
          label="6-digit code from the app"
          value={code}
          onValueChange={setCode}
          error={error}
        />
        <Button type="submit" loading={busy} className="w-full">
          Turn on two-factor
        </Button>
      </form>
      {cancel}
    </div>
  );
}

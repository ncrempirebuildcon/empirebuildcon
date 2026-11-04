/**
 * Shown on /contact instead of the site-visit form when no project is open for visits (task 5.8).
 * A visit is always for a project (the API requires one), so the form could never be sent.
 * Honest wording: it says only what is true now, and offers calls or WhatsApp only when the page
 * shows a number.
 */
export function VisitUnavailable({ canCall }: { canCall: boolean }) {
  return (
    <div className="flex flex-col gap-2" data-testid="visit-unavailable">
      <h2 className="font-display text-h3 font-semibold">Book a site visit</h2>
      <p className="text-body">
        No project is open for site visits right now. Send us a question below
        {canCall ? ", or call or WhatsApp us" : ""}.
      </p>
    </div>
  );
}

export default VisitUnavailable;

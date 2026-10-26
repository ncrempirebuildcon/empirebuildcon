/**
 * The API's development mailbox (only when the dev email transport is on and APP_ENV is
 * development or test; the route doesn't exist anywhere else): read the newest message sent to
 * an address and pick out a CMS link, like a person clicking it in their inbox.
 *
 * SECURITY: the links carry one-time tokens for throwaway accounts made in the run. They are
 * used once and never printed or written to disk; assertion messages show only the path.
 */
import { expect, type APIRequestContext } from "@playwright/test";

export interface DevMail {
  id: string;
  subject: string;
  /** Which email it is, e.g. "setup_link", "reset_link", "lead_alert". */
  template: string;
  links: string[];
}

/**
 * The newest message of one kind (`template`) to `email`, waiting up to `timeoutMs` for it.
 * `after` skips a message already seen (by id), e.g. an earlier link to the same person.
 */
export async function latestMail(
  request: APIRequestContext,
  email: string,
  options: { template: string; after?: string; timeoutMs?: number },
): Promise<DevMail> {
  let found: DevMail | null = null;
  const query = `to=${encodeURIComponent(email)}&template=${encodeURIComponent(options.template)}`;
  await expect
    .poll(
      async () => {
        const response = await request.get(`/api/v1/dev-mail/latest?${query}`);
        if (response.status() !== 200) return `status ${response.status()}`;
        const mail = (await response.json()) as DevMail;
        if (mail.id === options.after) return "only the earlier message";
        found = mail;
        return "arrived";
      },
      { timeout: options.timeoutMs ?? 15_000, message: `an email to the run's test address` },
    )
    .toBe("arrived");
  return found as unknown as DevMail;
}

/** The path, query and fragment of the first link in `mail` to `path` (e.g. "/admin/setup"). */
export function linkTo(mail: DevMail, path: string): string {
  for (const link of mail.links) {
    const url = new URL(link, "http://localhost");
    if (url.pathname === path) return `${url.pathname}${url.search}${url.hash}`;
  }
  throw new Error(`No ${path} link in the email "${mail.subject}".`);
}

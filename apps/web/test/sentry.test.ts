import { describe, expect, it } from "vitest";
import { beforeSendScrubber, sanitizeUrl } from "../src/lib/sentry-scrubber";

describe("Sentry data scrubber (beforeSend)", () => {
  it("sanitizes URLs by dropping query strings and fragments", () => {
    expect(sanitizeUrl("https://empirebuildcon.com/admin/leads?q=9876543210")).toBe(
      "https://empirebuildcon.com/admin/leads",
    );
    expect(sanitizeUrl("https://empirebuildcon.com/admin/reset#token=secret123")).toBe(
      "https://empirebuildcon.com/admin/reset",
    );
    expect(sanitizeUrl("/projects/aurum-heights?ref=campaign#specs")).toBe(
      "/projects/aurum-heights",
    );
  });

  it("strips request URL query strings, bodies, cookies, and IP from event", () => {
    const rawEvent = {
      request: {
        url: "https://empirebuildcon.com/admin/leads?q=9876543210#frag",
        data: { name: "Adarsh", mobile: "9876543210" },
        cookies: { session: "sess_secret_xyz" },
        headers: {
          cookie: "session=sess_secret_xyz",
          "x-empire-client-ip": "1.2.3.4",
          "x-forwarded-for": "1.2.3.4",
          "user-agent": "Mozilla/5.0",
        },
      },
      user: {
        id: "usr_123",
        ip_address: "1.2.3.4",
      },
      breadcrumbs: [
        {
          data: {
            url: "https://empirebuildcon.com/admin/leads?q=9876543210",
            to: "/admin/setup?token=one_time_token",
          },
        },
      ],
    };

    const scrubbed = beforeSendScrubber(rawEvent);

    // Request scrubbed
    expect(scrubbed.request?.url).toBe("https://empirebuildcon.com/admin/leads");
    expect(scrubbed.request?.data).toBeUndefined();
    expect(scrubbed.request?.cookies).toBeUndefined();
    expect(scrubbed.request?.headers?.cookie).toBeUndefined();
    expect(scrubbed.request?.headers?.["x-empire-client-ip"]).toBeUndefined();
    expect(scrubbed.request?.headers?.["user-agent"]).toBe("Mozilla/5.0");

    // User IP dropped
    expect(scrubbed.user?.ip_address).toBeUndefined();
    expect(scrubbed.user?.id).toBe("usr_123");

    // Breadcrumbs scrubbed
    expect(scrubbed.breadcrumbs?.[0]?.data?.url).toBe("https://empirebuildcon.com/admin/leads");
    expect(scrubbed.breadcrumbs?.[0]?.data?.to).toBe("/admin/setup");
  });
});

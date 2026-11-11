/**
 * The website side of the go-live check (task L8, RUNBOOK §3–§4): what a visitor's browser and a
 * search engine will see at a deployed address. Read-only: it only sends GET requests.
 *
 *   pnpm --filter @empire/qa golive -- https://staging.empirebuildcon.com
 *   pnpm --filter @empire/qa golive -- https://empirebuildcon.com --production \
 *     --alias https://empirebuildcon.in --alias https://www.empirebuildcon.com \
 *     --api-origin https://empire-api-xxxx.a.run.app
 *
 * --production   expect crawling allowed (ALLOW_INDEXING=true) and HSTS;
 *                without it, expect robots.txt to block crawling (staging).
 * --alias URL    another address that must redirect permanently to the main one (repeatable).
 * --api-origin   the Cloud Run address: without the edge key it must refuse (403, D-027).
 *
 * Prints PASS / WARN / FAIL per check; exit code 1 when anything fails.
 */

type Status = "PASS" | "WARN" | "FAIL";
interface Check {
  status: Status;
  name: string;
  detail: string;
}

const checks: Check[] = [];
const add = (status: Status, name: string, detail: string): void => {
  checks.push({ status, name, detail });
};

function parseArgs(argv: string[]): {
  base: URL;
  production: boolean;
  aliases: string[];
  apiOrigin?: string;
} {
  const rest = argv.filter((a) => a !== "--");
  const aliases: string[] = [];
  let production = false;
  let apiOrigin: string | undefined;
  let base: string | undefined;
  for (let i = 0; i < rest.length; i++) {
    const arg = rest[i];
    if (arg === "--production") production = true;
    else if (arg === "--alias") aliases.push(rest[++i] ?? "");
    else if (arg === "--api-origin") apiOrigin = rest[++i];
    else if (!base) base = arg;
  }
  if (!base) {
    console.error(
      "Usage: golive-check <https://site> [--production] [--alias URL] [--api-origin URL]",
    );
    process.exit(2);
  }
  return { base: new URL(base), production, aliases, apiOrigin };
}

async function get(url: string, follow = true): Promise<Response> {
  return fetch(url, {
    redirect: follow ? "follow" : "manual",
    headers: { "user-agent": "empire-golive-check" },
    signal: AbortSignal.timeout(20_000),
  });
}

async function attempt(name: string, run: () => Promise<void>): Promise<void> {
  try {
    await run();
  } catch (error) {
    add("FAIL", name, `request failed: ${(error as Error).message}`);
  }
}

async function main(): Promise<void> {
  const { base, production, aliases, apiOrigin } = parseArgs(process.argv.slice(2));
  const origin = base.origin;

  await attempt("home page", async () => {
    const res = await get(`${origin}/`);
    const html = await res.text();
    if (res.status !== 200) return add("FAIL", "home page", `status ${res.status}`);
    add("PASS", "home page", "200");
    const headers = res.headers;
    const csp =
      headers.get("content-security-policy") ?? headers.get("content-security-policy-report-only");
    if (!csp) add("FAIL", "security headers", "no Content-Security-Policy");
    else if (!headers.get("content-security-policy"))
      add(
        "WARN",
        "security headers",
        "CSP is report-only: set CSP_ENFORCE=true after the week on staging",
      );
    else add("PASS", "security headers", "CSP enforced");
    for (const [header, expected] of [
      ["x-content-type-options", "nosniff"],
      ["referrer-policy", "strict-origin-when-cross-origin"],
    ] as const) {
      if (headers.get(header) !== expected)
        add("FAIL", "security headers", `${header} is not ${expected}`);
    }
    if (production && !headers.get("strict-transport-security"))
      add("FAIL", "security headers", "no Strict-Transport-Security");
    if (!/<title>[^<]+<\/title>/.test(html)) add("FAIL", "home page", "no <title>");
    if (/\[DRAFT|\[TBD\]|Sample — /.test(html))
      add("FAIL", "home page", "draft, [TBD] or sample text on the home page");
  });

  await attempt("robots.txt", async () => {
    const res = await get(`${origin}/robots.txt`);
    const text = await res.text();
    const blocked = /^Disallow:\s*\/\s*$/m.test(text);
    if (res.status !== 200) add("FAIL", "robots.txt", `status ${res.status}`);
    else if (production && blocked)
      add(
        "FAIL",
        "robots.txt",
        "crawling is blocked: set ALLOW_INDEXING=true and redeploy (RUNBOOK §4.6)",
      );
    else if (!production && !blocked)
      add("FAIL", "robots.txt", "crawling is allowed on a non-production site");
    else add("PASS", "robots.txt", production ? "crawling allowed" : "crawling blocked (staging)");
    if (!text.includes(`Sitemap: ${origin}/sitemap.xml`))
      add("FAIL", "robots.txt", `no "Sitemap: ${origin}/sitemap.xml" line (check SITE_URL)`);
  });

  let projectUrl: string | undefined;
  await attempt("sitemap", async () => {
    const res = await get(`${origin}/sitemap.xml`);
    const xml = await res.text();
    const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1] ?? "");
    if (res.status !== 200 || locs.length === 0)
      return add("FAIL", "sitemap", `status ${res.status}, ${locs.length} address(es)`);
    const foreign = locs.filter((loc) => !loc.startsWith(`${origin}/`) && loc !== origin);
    if (foreign.length)
      add("FAIL", "sitemap", `addresses on another host: ${foreign.slice(0, 3).join(", ")}`);
    else add("PASS", "sitemap", `${locs.length} address(es)`);
    projectUrl = locs.find((loc) => /\/projects\/[^/]+$/.test(loc));
  });

  await attempt("project page", async () => {
    if (!projectUrl) return add("FAIL", "project page", "no project in the sitemap");
    const res = await get(projectUrl);
    const html = await res.text();
    const rera = /UP-?RERA/i.test(html);
    const link = html.includes("up-rera.in");
    if (res.status === 200 && rera && link)
      add("PASS", "project page", `${new URL(projectUrl).pathname} shows UP-RERA and up-rera.in`);
    else
      add(
        "FAIL",
        "project page",
        `${projectUrl}: status ${res.status}, UP-RERA ${rera}, up-rera.in ${link} (D-002)`,
      );
  });

  await attempt("API through the site", async () => {
    const res = await get(`${origin}/api/health/live`);
    const body = await res.text();
    if (res.status === 200 && body.includes('"ok"'))
      add("PASS", "API through the site", "/api/health/live ok");
    else
      add(
        "FAIL",
        "API through the site",
        `status ${res.status}: check API_ORIGIN and EDGE_PROXY_KEY`,
      );
  });

  if (base.protocol === "https:") {
    await attempt("https redirect", async () => {
      const res = await get(`http://${base.host}/`, false);
      const to = res.headers.get("location") ?? "";
      if ([301, 307, 308].includes(res.status) && to.startsWith("https://"))
        add("PASS", "https redirect", `http → ${to}`);
      else add("FAIL", "https redirect", `http answered ${res.status} ${to}`);
    });
  }

  for (const alias of aliases) {
    await attempt(`alias ${alias}`, async () => {
      const res = await get(alias, false);
      const to = res.headers.get("location") ?? "";
      if ([301, 308].includes(res.status) && to.startsWith(origin))
        add("PASS", `alias ${alias}`, `${res.status} → ${to}`);
      else
        add(
          "FAIL",
          `alias ${alias}`,
          `answered ${res.status} ${to}, expected a permanent redirect to ${origin}`,
        );
    });
  }

  if (apiOrigin) {
    await attempt("edge guard", async () => {
      const res = await get(`${apiOrigin.replace(/\/$/, "")}/api/v1/public/site`, false);
      if (res.status === 403)
        add("PASS", "edge guard", "the API refuses calls without the edge key (D-027)");
      else add("FAIL", "edge guard", `the API answered ${res.status} without the edge key`);
    });
  }

  for (const check of checks)
    console.log(`${check.status.padEnd(4)}  ${check.name}: ${check.detail}`);
  const failed = checks.filter((c) => c.status === "FAIL").length;
  const warned = checks.filter((c) => c.status === "WARN").length;
  console.log(`\n${failed} to fix, ${warned} to look at, ${checks.length - failed - warned} fine.`);
  process.exit(failed ? 1 : 0);
}

await main();

export {};

/**
 * Lighthouse budgets for the public site (task 5.7, D-049): mobile Lighthouse (its default:
 * a mid-range phone on a slow 4G connection, simulated) on the home page, the projects list, a
 * project, a home, the properties list and the contact page.
 *
 * Budgets, each the median of three runs per page:
 *   - performance ≥ 90, accessibility ≥ 95, best practices ≥ 95;
 *   - SEO ≥ 90, counted without "is-crawlable": the whole site is `noindex` until go-live
 *     (Phase 9 gate), which that one audit reports by design. Every other SEO audit counts.
 *
 * Run alone (`pnpm --filter @empire/qa lighthouse`, CI job "lighthouse"): scores need a quiet
 * machine. The reports are saved under test-results/lighthouse/ for a look at what slipped.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect, test } from "@playwright/test";
import * as chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";
import puppeteer, { type Browser, type Page } from "puppeteer-core";
import { CMS_STATE } from "../lib/auth";
import { catalogueProject } from "../lib/catalogue";
import { WEB_URL } from "../lib/env";

test.use({ storageState: CMS_STATE });

const RUNS = 3;
const BUDGET = { performance: 90, accessibility: 95, "best-practices": 95, seo: 90 } as const;
/**
 * WHY each run in its own browser context: on GitHub's runner (Chrome 156) every Lighthouse run's
 * new tab landed on the previous run's localhost renderer (same process id, older each run) and,
 * while committing the document, spent 165–245 ms on that process's leftover garbage collection:
 * one "unattributable" task that Lighthouse's 4× CPU simulation turns into ~700–1000 ms of
 * blocking time (performance ~93 → ~72, D-049). Turning off ProcessPerSiteUpToMainFrameThreshold
 * didn't stop the reuse. Chrome never shares a renderer between browser contexts, so a fresh
 * context per run, closed afterwards, gives each run a new process, as a first visit has.
 * The summary counts runs that still landed on an earlier run's process.
 */
async function freshPage(browser: Browser): Promise<{ page: Page; done: () => Promise<void> }> {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  return { page, done: () => context.close() };
}

/** The renderer process that committed the page's document, from the run's trace. */
function rendererOf(trace: unknown): number | undefined {
  const events =
    (
      trace as
        | {
            traceEvents?: {
              name?: string;
              args?: {
                data?: { processId?: number; url?: string; isOutermostMainFrame?: boolean };
              };
            }[];
          }
        | undefined
    )?.traceEvents ?? [];
  const commit = events.find(
    (e) =>
      e.name === "FrameCommittedInBrowser" &&
      e.args?.data?.isOutermostMainFrame &&
      e.args.data.url?.startsWith("http"),
  );
  return commit?.args?.data?.processId;
}
/** A run with more blocking time than this keeps its trace for diagnosis (at most 2 per job). */
const TRACE_OVER_MS = 500;
/**
 * TODO(phase-5): make performance a hard budget again once 5.7c lands (owner, 4 Nov 2026, D-049).
 * With the renderer reuse fixed, CI and the workspace both score 85–91: React hydration
 * (react-dom, ~73 KB) and, on localhost, Lighthouse timing the LCP after the scripts. Until the
 * client JavaScript is cut, a performance miss is a warning; the other three budgets fail the job.
 */
const WARN_ONLY: ReadonlySet<string> = new Set(["performance"]);
type Category = keyof typeof BUDGET;
const OUT = resolve(import.meta.dirname, "..", "test-results", "lighthouse");

interface Lhr {
  categories: Record<string, { score: number | null; auditRefs: { id: string; weight: number }[] }>;
  audits: Record<string, { score: number | null; displayValue?: string }>;
}

/** A category's score out of 100; SEO leaves out "is-crawlable" (noindex before go-live). */
function categoryScore(lhr: Lhr, name: Category): number {
  const category = lhr.categories[name];
  if (!category) return 0;
  if (name !== "seo") return Math.round((category.score ?? 0) * 100);
  let total = 0;
  let weight = 0;
  for (const ref of category.auditRefs) {
    if (ref.id === "is-crawlable" || ref.weight === 0) continue;
    // An audit that errored scores 0 (Lighthouse fails the whole category in that case).
    const score = lhr.audits[ref.id]?.score ?? 0;
    total += score * ref.weight;
    weight += ref.weight;
  }
  return weight ? Math.round((total / weight) * 100) : 0;
}

/**
 * The CPU slowdown that makes this host behave like a mid-tier phone, from Lighthouse's own
 * table (docs/throttling.md): high-end desktop (benchmark 1500–2000) 4×, low-end desktop
 * (1000–1500) 2×, high-end mobile (800–1200) 2×, in between by the benchmark, never below 1×
 * and never above Lighthouse's default 4×.
 */
function cpuMultiplier(benchmarkIndex: number | undefined): number {
  if (!benchmarkIndex || !Number.isFinite(benchmarkIndex)) return 4;
  const value = benchmarkIndex / 375;
  return Math.round(Math.min(4, Math.max(1, value)) * 10) / 10;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)] ?? 0;
}

test("the public pages meet the Lighthouse budgets on a phone", async ({ page }) => {
  test.setTimeout(15 * 60_000);
  const project = await catalogueProject(page);
  const paths = [
    "/",
    "/projects",
    `/projects/${project.slug}`,
    `/projects/${project.slug}/${project.configSlugs[0]}`,
    "/properties",
    "/contact",
  ];
  mkdirSync(OUT, { recursive: true });
  const chrome = await chromeLauncher.launch({
    chromePath: process.env.PW_CHROMIUM_PATH || chromium.executablePath(),
    chromeFlags: ["--headless=new", "--no-sandbox"],
  });
  const browser = await puppeteer.connect({
    browserURL: `http://127.0.0.1:${chrome.port}`,
    defaultViewport: null,
  });
  const misses: string[] = [];
  const warnings: string[] = [];
  let tracesKept = 0;
  const table: string[] = [];
  const renderers = new Set<number>();
  let reused = 0;
  let measured = 0;
  try {
    // Calibration (Lighthouse docs/throttling.md): the default 4× CPU slowdown assumes a
    // high-end desktop host. A slower host (a CI runner) would then simulate a phone far slower
    // than the mid-tier phone we target. This run also warms the server.
    const warm = await freshPage(browser);
    const probe = await lighthouse(`${WEB_URL}/`, { logLevel: "error" }, undefined, warm.page);
    await warm.done();
    const probePid = rendererOf(probe?.artifacts?.Trace);
    if (probePid) renderers.add(probePid);
    const benchmark = (probe?.lhr as unknown as { environment?: { benchmarkIndex?: number } })
      ?.environment?.benchmarkIndex;
    const cpu = cpuMultiplier(benchmark);
    const agent = (probe?.lhr as unknown as { environment?: { hostUserAgent?: string } })
      ?.environment?.hostUserAgent;
    table.push(`host benchmarkIndex ${Math.round(benchmark ?? 0)} → CPU slowdown ${cpu}×`);
    table.push(`browser ${agent?.match(/(?:Headless)?Chrome\/[\d.]+/)?.[0] ?? "unknown"}`);
    for (const path of paths) {
      const scores: Record<Category, number[]> = {
        performance: [],
        accessibility: [],
        "best-practices": [],
        seo: [],
      };
      for (let run = 0; run < RUNS; run += 1) {
        const fresh = await freshPage(browser);
        const result = await lighthouse(
          `${WEB_URL}${path}`,
          {
            output: ["json", "html"],
            throttling: { cpuSlowdownMultiplier: cpu },
            logLevel: "error",
          },
          undefined,
          fresh.page,
        );
        await fresh.done();
        const lhr = result?.lhr as unknown as Lhr | undefined;
        const html = Array.isArray(result?.report) ? result.report[1] : undefined;
        expect(lhr, `${path}: Lighthouse ran`).toBeTruthy();
        if (!lhr) continue;
        for (const name of Object.keys(BUDGET) as Category[]) {
          scores[name].push(categoryScore(lhr, name));
        }
        const file = `${path.replace(/[^a-z0-9]+/gi, "_") || "home"}-${run + 1}.json`;
        const blocking = Number(
          (lhr.audits["total-blocking-time"] as { numericValue?: number } | undefined)
            ?.numericValue ?? 0,
        );
        const trace = (result?.artifacts as { Trace?: unknown } | undefined)?.Trace;
        const pid = rendererOf(trace);
        if (pid) {
          measured += 1;
          if (renderers.has(pid)) reused += 1;
          renderers.add(pid);
        }
        if (blocking > TRACE_OVER_MS && trace && tracesKept < 2) {
          // Opens in Chrome DevTools → Performance → Load profile.
          writeFileSync(
            resolve(OUT, file.replace(/\.json$/, ".trace.json")),
            JSON.stringify(trace),
          );
          tracesKept += 1;
        }
        writeFileSync(resolve(OUT, file), JSON.stringify(lhr));
        if (typeof html === "string")
          writeFileSync(resolve(OUT, file.replace(/json$/, "html")), html);
      }
      const line = (Object.keys(BUDGET) as Category[]).map((name) => {
        const value = median(scores[name]);
        if (value < BUDGET[name]) {
          const miss = `${path}: ${name} ${value} < ${BUDGET[name]}`;
          if (WARN_ONLY.has(name)) warnings.push(miss);
          else misses.push(miss);
        }
        return `${name} ${value}`;
      });
      table.push(`${path}  ${line.join(" · ")}`);
    }
    table.push(`renderer: ${reused} of ${measured} runs reused an earlier run's process`);
  } finally {
    await browser.disconnect();
    await chrome.kill();
  }
  writeFileSync(resolve(OUT, "summary.txt"), `${table.join("\n")}\n`);
  console.log(table.join("\n"));
  if (warnings.length > 0) {
    // Shown in the report and in the CI log; it doesn't fail the job (WARN_ONLY above).
    test.info().annotations.push({ type: "warning", description: warnings.join("; ") });
    console.warn(`Lighthouse budget warnings (not failing):\n${warnings.join("\n")}`);
    writeFileSync(resolve(OUT, "warnings.txt"), `${warnings.join("\n")}\n`);
  }
  expect(misses, misses.join("\n")).toEqual([]);
});

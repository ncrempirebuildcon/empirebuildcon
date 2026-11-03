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
import { CMS_STATE } from "../lib/auth";
import { catalogueProject } from "../lib/catalogue";
import { WEB_URL } from "../lib/env";

test.use({ storageState: CMS_STATE });

const RUNS = 3;
const BUDGET = { performance: 90, accessibility: 95, "best-practices": 95, seo: 90 } as const;
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
    const score = lhr.audits[ref.id]?.score;
    if (ref.id === "is-crawlable" || ref.weight === 0 || score == null) continue;
    total += score * ref.weight;
    weight += ref.weight;
  }
  return weight ? Math.round((total / weight) * 100) : 0;
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
  const misses: string[] = [];
  const table: string[] = [];
  try {
    for (const path of paths) {
      const scores: Record<Category, number[]> = {
        performance: [],
        accessibility: [],
        "best-practices": [],
        seo: [],
      };
      for (let run = 0; run < RUNS; run += 1) {
        const result = await lighthouse(`${WEB_URL}${path}`, {
          port: chrome.port,
          output: "json",
          logLevel: "error",
        });
        const lhr = result?.lhr as unknown as Lhr | undefined;
        expect(lhr, `${path}: Lighthouse ran`).toBeTruthy();
        if (!lhr) continue;
        for (const name of Object.keys(BUDGET) as Category[]) {
          scores[name].push(categoryScore(lhr, name));
        }
        const file = `${path.replace(/[^a-z0-9]+/gi, "_") || "home"}-${run + 1}.json`;
        writeFileSync(resolve(OUT, file), JSON.stringify(lhr));
      }
      const line = (Object.keys(BUDGET) as Category[]).map((name) => {
        const value = median(scores[name]);
        if (value < BUDGET[name]) misses.push(`${path}: ${name} ${value} < ${BUDGET[name]}`);
        return `${name} ${value}`;
      });
      table.push(`${path}  ${line.join(" · ")}`);
    }
  } finally {
    await chrome.kill();
  }
  writeFileSync(resolve(OUT, "summary.txt"), `${table.join("\n")}\n`);
  console.log(table.join("\n"));
  expect(misses, misses.join("\n")).toEqual([]);
});

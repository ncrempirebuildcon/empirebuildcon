"use client";
/**
 * Project card for chat citations (Phase 7 Task 7.3, Scope 2).
 *
 * COMPLIANCE (AGENTS.md & Task 7.3):
 * - Project details, name, and UP-RERA number are fetched strictly from the public
 *   API (/api/v1/public/projects/{slug}).
 * - NEVER parses facts, RERA numbers, or prices from the model's answer text.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { CHAT_COPY } from "./copy";

interface ProjectCardData {
  name: string;
  reraNumber?: string | null;
  reraUrl?: string | null;
}

export function ProjectCard({ slug }: { slug: string }) {
  const [data, setData] = useState<ProjectCardData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadProject() {
      try {
        const res = await fetch(`/api/v1/public/projects/${encodeURIComponent(slug)}`, {
          headers: { Accept: "application/json" },
        });
        if (!res.ok) {
          if (!cancelled) setFailed(true);
          return;
        }
        const json = await res.json();
        if (!cancelled && json && typeof json === "object") {
          const reraNumber = typeof json.rera?.number === "string" ? json.rera.number : null;
          const reraUrl =
            typeof json.rera?.url === "string" && json.rera.url
              ? json.rera.url
              : "https://www.up-rera.in";
          setData({
            name: typeof json.name === "string" ? json.name : slug,
            reraNumber,
            reraUrl,
          });
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    }

    void loadProject();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (failed) return null;

  return (
    <div className="mt-2 rounded-xl border border-gold-500/30 bg-noir-900/80 p-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        <strong className="font-display font-semibold text-sand-100">
          {data ? data.name : slug}
        </strong>
        <Link
          href={`/projects/${encodeURIComponent(slug)}`}
          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center text-[11px] font-bold text-gold-400 underline hover:text-gold-300"
        >
          {CHAT_COPY.viewProject}
        </Link>
      </div>
      {data?.reraNumber && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-sand-400">
          <span>
            {CHAT_COPY.reraPrefix} {data.reraNumber}
          </span>
          <a
            href={data.reraUrl || "https://www.up-rera.in"}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-[44px] items-center text-gold-400 underline hover:text-gold-300"
          >
            {CHAT_COPY.verifyRera}
          </a>
        </div>
      )}
    </div>
  );
}

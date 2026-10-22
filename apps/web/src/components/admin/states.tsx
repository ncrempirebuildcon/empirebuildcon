"use client";
/**
 * Page states for CMS screens (handbook/DESIGN_SYSTEM.md §8 "States"): loading skeletons,
 * "Couldn't load" with Try again, an honest empty message with a next step, and the placeholder
 * for features that arrive in a later update.
 */
import type { ReactNode } from "react";
import { Alert, Button, Skeleton } from "@empire/ui";

/** Skeleton rows while data loads. `label` is read by screen readers ("Loading projects…"). */
export function LoadingPanel({ label, rows = 4 }: { label: string; rows?: number }) {
  return (
    <div
      aria-busy="true"
      className="flex flex-col gap-3 rounded-card border border-line bg-noir-800 p-5"
    >
      <p className="sr-only" role="status">
        {label}
      </p>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-6 w-full" />
      ))}
    </div>
  );
}

/** "Couldn't load …" with a Try again button. Announced immediately (role="alert"). */
export function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Alert tone="error" title={message}>
      <p className="mb-3">Check your connection, then try again.</p>
      <Button variant="secondary" onClick={onRetry}>
        Try again
      </Button>
    </Alert>
  );
}

/** An honest empty state: what is missing and what to do next. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 px-4 py-8 text-center">
      <p className="text-base font-bold text-ivory">{title}</p>
      {children}
    </div>
  );
}

/**
 * Placeholder for media features (uploads, floor plans, the RERA QR image, share images), which
 * arrive with the media manager.
 * TODO(phase-4): replace every use with the media manager in part 2.
 */
export function MediaPlaceholder({ what }: { what?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-tile border border-dashed border-gold-line-strong bg-noir-700 px-4 py-3 text-small">
      <strong className="text-ivory">Media manager arrives in the next update</strong>
      {what ? <span className="text-muted">{what}</span> : null}
    </div>
  );
}

/** A CMS card with a heading, optional description and optional actions on the right. */
export function Panel({
  title,
  description,
  actions,
  children,
  headingLevel = 2,
  id,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  headingLevel?: 2 | 3;
  id?: string;
  className?: string;
}) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section
      aria-labelledby={id ? `${id}-title` : undefined}
      className={`flex flex-col gap-4 rounded-card border border-line bg-noir-800 p-4.5 ${className ?? ""}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <Heading id={id ? `${id}-title` : undefined} className="text-[17px] font-bold">
            {title}
          </Heading>
          {description ? <div className="mt-0.5 text-caption text-muted">{description}</div> : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

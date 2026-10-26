"use client";
/**
 * The audit log (board NoirCmsAudit, `audit.read`): every sign-in, change, publish, export,
 * permission change and erasure, newest first, with who did it, the masked IP and the
 * before/after values. Filters live in the address (`?person=<id>|system&action=&from=&to=&page=`);
 * dates are whole days in India time (the API counts them in IST, `to` included).
 *
 * INVARIANT (API): audit rows are append-only; this screen only reads them. IPs arrive masked
 * from the API (platform/crypto.py `mask_ip`), and `changes` never holds personal free text.
 */
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Select, TextField, cx } from "@empire/ui";
import { isCalendarDate } from "@empire/ui/format";
import { api, call } from "@/lib/api";
import { AUDIT_ACTION_FILTERS, actionQuery, type AuditActionFilter } from "@/lib/audit";
import { formatCalendarDate } from "@/lib/dates";
import { problemMessage } from "@/lib/problems";
import { AUDIT_PATH } from "@/lib/routes";
import { Pager, pageFrom } from "@/components/admin/Pager";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../session-context";
import { AuditEntries } from "./AuditEntries";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PER_PAGE = 50;

/** "system": entries made by the system itself (no person). */
const SYSTEM = "system";

interface Filters {
  person: string;
  action: AuditActionFilter | "";
  from: string;
  to: string;
  page: number;
}

function readFilters(params: URLSearchParams): Filters {
  const person = params.get("person") ?? "";
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  return {
    person: person === SYSTEM || UUID_RE.test(person) ? person : "",
    action:
      (Object.keys(AUDIT_ACTION_FILTERS) as AuditActionFilter[]).find(
        (key) => key === params.get("action"),
      ) ?? "",
    from: isCalendarDate(from) ? from : "",
    to: isCalendarDate(to) ? to : "",
    page: pageFrom(params.get("page")),
  };
}

function hrefFor(filters: Filters): string {
  const search = new URLSearchParams();
  if (filters.person) search.set("person", filters.person);
  if (filters.action) search.set("action", filters.action);
  if (filters.from) search.set("from", filters.from);
  if (filters.to) search.set("to", filters.to);
  if (filters.page > 1) search.set("page", String(filters.page));
  const query = search.toString();
  return query ? `${AUDIT_PATH}?${query}` : AUDIT_PATH;
}

export function AuditScreen() {
  const filters = readFilters(useSearchParams());
  const { can } = useAdminSession();
  const filtered = Boolean(filters.person || filters.action || filters.from || filters.to);
  const key = `audit:${hrefFor(filters)}`;
  const list = useLoad(key, () =>
    call(
      api.GET("/api/v1/admin/audit-log", {
        params: {
          query: {
            actor_id: filters.person && filters.person !== SYSTEM ? filters.person : undefined,
            system: filters.person === SYSTEM ? true : undefined,
            ...actionQuery(filters.action),
            from: filters.from || undefined,
            to: filters.to || undefined,
            page: filters.page,
            per_page: PER_PAGE,
          },
        },
      }),
    ),
  );
  // The people for the Person filter: every account for the super-admin (users.manage); admins
  // (no users.manage) get the people who can own leads, the only staff list their role may read.
  // TODO(phase-6): a list of the people who appear in the log, for every audit.read holder.
  const everyone = can("users.manage");
  const people = useLoad(`audit-people:${everyone}`, async () => {
    if (everyone) {
      const answer = await call(
        api.GET("/api/v1/admin/users", { params: { query: { per_page: 100 } } }),
      );
      return answer.items.map((user) => ({ value: user.id, label: user.name }));
    }
    if (!can("leads.read")) return [];
    const owners = await call(api.GET("/api/v1/admin/lead-owners")).catch(() => []);
    return owners.map((owner) => ({ value: owner.id, label: owner.name }));
  });

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3.5">
        <p className="min-w-0 flex-[1_1_320px] text-small text-muted">
          Every sign-in, change, publish, export, permission change and erasure, with who did it and
          from where.
        </p>
        <span className="inline-flex items-center gap-2 rounded-pill border border-gold-500/60 px-3 py-1.5 text-caption font-bold text-gold-300">
          <LockIcon />
          Audit entries can&apos;t be edited or deleted
        </span>
      </div>

      <AuditFilters
        key={hrefFor({ ...filters, page: 1 })}
        filters={filters}
        people={people.data ?? []}
        partialPeople={!everyone}
      />

      <section
        aria-labelledby="audit-entries-title"
        className="flex flex-col overflow-hidden rounded-card border border-line bg-noir-800"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4.5 py-3 text-small">
          <h2 id="audit-entries-title" className="font-bold text-ivory">
            {list.data ? countLabel(list.data.meta.total, filtered) : "Audit entries"}
          </h2>
          <span className="text-caption text-muted">
            Newest first · times in IST · IP addresses shown masked
          </span>
        </div>
        {list.error ? (
          <ErrorPanel
            message={problemMessage(list.error, "Couldn't load the audit log.")}
            onRetry={list.reload}
          />
        ) : !list.data ? (
          <LoadingPanel label="Loading the audit log…" rows={8} />
        ) : list.data.items.length === 0 ? (
          <EmptyState
            title={filtered ? "No entries match these filters" : "Nothing has been recorded yet"}
          >
            {filtered ? (
              <>
                <span>Try another person, action or dates.</span>
                <Link
                  href={AUDIT_PATH}
                  className="inline-flex min-h-11 items-center font-bold underline"
                >
                  Clear filters
                </Link>
              </>
            ) : (
              <span>Sign-ins and changes appear here as soon as they happen.</span>
            )}
          </EmptyState>
        ) : (
          <>
            <AuditEntries entries={list.data.items} />
            <div className="border-t border-line px-4 py-2">
              <Pager
                page={list.data.meta.page}
                perPage={list.data.meta.per_page}
                total={list.data.meta.total}
                pages={list.data.meta.pages}
                hrefFor={(page) => hrefFor({ ...filters, page })}
                noun="entries"
                singular="entry"
              />
            </div>
          </>
        )}
        <p className="border-t border-line px-4.5 py-3 text-caption text-muted">
          Only the super-admin and admins can read this log. Entries are kept for [retention
          period]; the database refuses edits and deletes on this table.
        </p>
      </section>
    </>
  );
}

function countLabel(total: number, filtered: boolean): string {
  const noun = total === 1 ? "entry" : "entries";
  return filtered ? `${total} ${noun} match` : `${total} ${noun}`;
}

function AuditFilters({
  filters,
  people,
  partialPeople,
}: {
  filters: Filters;
  people: Array<{ value: string; label: string }>;
  /** True when the list holds only the people who can own leads (no users.manage). */
  partialPeople: boolean;
}) {
  const [from, setFrom] = useState(filters.from);
  const [to, setTo] = useState(filters.to);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const href = (patch: Partial<Filters>) => hrefFor({ ...filters, ...patch, page: 1 });
  const go = (patch: Partial<Filters>) => router.replace(href(patch), { scroll: false });

  function onDates(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (from && to && from > to) {
      setError(`The first date must be on or before ${formatCalendarDate(to)}.`);
      return;
    }
    setError(null);
    go({ from, to });
  }

  return (
    <section
      aria-label="Filters"
      className="flex flex-col gap-3 rounded-card border border-line bg-noir-800 px-4 py-3.5"
    >
      <div className="flex flex-wrap items-end gap-x-4.5 gap-y-3">
        <Select
          label="Person"
          value={filters.person}
          placeholder="Everyone"
          options={[{ value: SYSTEM, label: "System (automatic)" }, ...people]}
          hint={
            partialPeople
              ? "Your role can list the people who own leads; other people's entries show under Everyone."
              : undefined
          }
          onChange={(event) => go({ person: event.target.value })}
          className="flex-[1_1_220px]"
        />
        <form
          aria-label="Dates (India time)"
          onSubmit={onDates}
          className="flex flex-[2_1_420px] flex-wrap items-end gap-3"
        >
          <TextField
            label="From (IST)"
            type="date"
            value={from}
            error={error ?? undefined}
            onChange={(event) => setFrom(event.target.value)}
            className="flex-[1_1_160px]"
          />
          <TextField
            label="Until (IST)"
            type="date"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            className="flex-[1_1_160px]"
          />
          <Button type="submit" variant="secondary" className="mb-0.75">
            Apply dates
          </Button>
        </form>
      </div>
      <div role="group" aria-label="Action" className="flex flex-wrap items-center gap-1.5">
        <KindLink href={href({ action: "" })} pressed={filters.action === ""}>
          All
        </KindLink>
        {(Object.keys(AUDIT_ACTION_FILTERS) as AuditActionFilter[]).map((key) => (
          <KindLink key={key} href={href({ action: key })} pressed={filters.action === key}>
            {AUDIT_ACTION_FILTERS[key].label}
          </KindLink>
        ))}
      </div>
    </section>
  );
}

function KindLink({
  href,
  pressed,
  children,
}: {
  href: string;
  pressed: boolean;
  children: string;
}) {
  return (
    <Link
      href={href}
      aria-current={pressed ? "true" : undefined}
      className={cx(
        "inline-flex min-h-11 items-center rounded-pill border px-3.5 text-caption",
        pressed
          ? "border-gold-500 bg-gold-tint font-extrabold text-gold-300"
          : "border-line-strong bg-noir-700 font-semibold text-body hover:text-gold-300",
      )}
    >
      {children}
    </Link>
  );
}

function LockIcon() {
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
    >
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

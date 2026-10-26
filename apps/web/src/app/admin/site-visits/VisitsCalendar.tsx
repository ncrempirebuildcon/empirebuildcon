"use client";
/**
 * The site-visit calendar (/admin/site-visits, board NoirCmsVisits): week, day and list views of
 * the visits, filters for status and project, and a side panel to confirm, reschedule, complete,
 * mark a no-show or cancel the selected visit. Times are India time (IST).
 *
 * The view, the date, the filters and the open visit live in the address
 * (`?view=week|day|list&date=2026-10-24&status=&open=true&project_id=&visit=`), so a visit can be linked
 * from the dashboard or a lead; the dashboard's `?from=&to=` count links open the right day or
 * week too. Without `view`, phones get the list (it reads top to bottom with
 * no sideways scrolling) and wider screens the week.
 *
 * SECURITY: needs `site_visits.manage`; the API checks it again and limits a sales user to
 * visits of their own leads (SECURITY.md §1).
 */
import Link from "next/link";
import {
  useMemo,
  useOptimistic,
  useRef,
  useState,
  useSyncExternalStore,
  useTransition,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { LiveRegion, SegmentedControl, Select, maskPhone } from "@empire/ui";
import { addDays, isCalendarDate, istToday, startOfWeek } from "@empire/ui/format";
import { api, call } from "@/lib/api";
import { formatCalendarDate, formatDayLabel, formatWeekRange } from "@/lib/dates";
import { VISIT_STATUS_SHORT, type SiteVisit, type VisitStatus } from "@/lib/leads/labels";
import { problemMessage } from "@/lib/problems";
import { SITE_VISITS_PATH, leadPath } from "@/lib/routes";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { ContactLinks } from "@/components/admin/leads/ContactLinks";
import { VisitEditor } from "@/components/admin/leads/VisitEditor";
import { useProjectOptions, useStaffOptions } from "@/components/admin/leads/useLeadOptions";
import { useAdminSession } from "../session-context";
import { DayView, ListView, WeekView } from "./CalendarViews";

type View = "week" | "day" | "list";

interface CalendarState {
  /** Null when the address doesn't say: then the screen width decides (list on phones). */
  view: View | null;
  date: string;
  status: VisitStatus | "";
  /** "true": requested or confirmed only (the dashboard's visit counts); "false": the rest. */
  open: "" | "true" | "false";
  project_id: string;
  visit: string;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The calendar state in an address. Besides its own `view` and `date` it reads the dashboard's
 * links, `?from=…&to=…` (the API builds them): one day opens the day view, a longer range the
 * week that holds `from`, in the screen's default view.
 */
function readState(params: URLSearchParams): CalendarState {
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const fromLink = isCalendarDate(from) ? from : "";
  // A range keeps the screen's default (week, or the list on a phone).
  const linkedView: View | null = fromLink && to === from ? "day" : null;
  const view = params.get("view") ?? linkedView;
  const date = params.get("date") ?? fromLink;
  const status = params.get("status") ?? "";
  const project = params.get("project_id") ?? "";
  const visit = params.get("visit") ?? "";
  return {
    view: view === "week" || view === "day" || view === "list" ? view : null,
    date: isCalendarDate(date) ? date : istToday(),
    status: Object.hasOwn(VISIT_STATUS_SHORT, status) ? (status as VisitStatus) : "",
    open: params.get("open") === "true" ? "true" : params.get("open") === "false" ? "false" : "",
    project_id: UUID_RE.test(project) ? project : "",
    visit: UUID_RE.test(visit) ? visit : "",
  };
}

function calendarHref(state: CalendarState): string {
  const search = new URLSearchParams();
  if (state.view) search.set("view", state.view);
  if (state.date !== istToday()) search.set("date", state.date);
  if (state.status) search.set("status", state.status);
  if (state.open) search.set("open", state.open);
  if (state.project_id) search.set("project_id", state.project_id);
  if (state.visit) search.set("visit", state.visit);
  const query = search.toString();
  return query ? `${SITE_VISITS_PATH}?${query}` : SITE_VISITS_PATH;
}

// WHY useSyncExternalStore: the default view follows the screen width, which only the browser
// knows; the server renders the week and React switches after hydration without a mismatch.
const PHONE_QUERY = "(max-width: 639px)";
function subscribePhone(onChange: () => void) {
  const media = window.matchMedia(PHONE_QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
const isPhone = () => window.matchMedia(PHONE_QUERY).matches;

export function VisitsCalendar() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { can } = useAdminSession();
  const state = useMemo(() => readState(params), [params]);
  const phone = useSyncExternalStore(subscribePhone, isPhone, () => false);
  const projects = useProjectOptions();
  const staff = useStaffOptions(can("site_visits.manage"));
  const panelHeading = useRef<HTMLHeadingElement>(null);
  const [announcement, setAnnouncement] = useState("");

  const [, startTransition] = useTransition();
  const [shown, setShown] = useOptimistic(
    state,
    (_current: CalendarState, next: CalendarState) => next,
  );
  const view: View = shown.view ?? (phone ? "list" : "week");
  // Edits in the visit panel not saved yet: moving the calendar (another visit, week, view or
  // filter) would close the panel and lose them, so it asks first, like leaving the page.
  const [panelDirty, setPanelDirty] = useState(false);
  const { dialog: leaveDialog, leave } = useUnsavedChanges(panelDirty);
  function go(next: Partial<CalendarState>) {
    const target = { ...state, ...next };
    if (calendarHref(target) === calendarHref(state)) return;
    if (panelDirty) {
      leave(calendarHref(target), { replace: true });
      return;
    }
    startTransition(() => {
      setShown(target);
      router.replace(calendarHref(target), { scroll: false });
    });
  }

  const range =
    view === "day"
      ? { from: state.date, to: state.date }
      : { from: startOfWeek(state.date), to: addDays(startOfWeek(state.date), 6) };
  const visits = useLoad(
    `visits:${range.from}:${range.to}:${state.status}:${state.open}:${state.project_id}`,
    () =>
      call(
        api.GET("/api/v1/admin/site-visits", {
          params: {
            query: {
              from: range.from,
              to: range.to,
              status: state.status || undefined,
              open: state.open ? state.open === "true" : undefined,
              project_id: state.project_id || undefined,
            },
          },
        }),
      ),
  );
  const list = visits.data ?? [];
  const selected = list.find((visit) => visit.id === state.visit) ?? null;

  function select(visit: SiteVisit) {
    const willAsk = panelDirty && visit.id !== state.visit;
    go({ visit: visit.id });
    // WHY: on a phone the panel is below the list; move focus there so keyboard and screen-reader
    // users land on the form they asked for. Not while the "Leave without saving?" question is up.
    if (!willAsk) requestAnimationFrame(() => panelHeading.current?.focus());
  }

  const step = view === "day" ? 1 : 7;
  const unit = view === "day" ? "day" : "week";
  const heading =
    view === "day"
      ? formatDayLabel(state.date) + " " + state.date.slice(0, 4)
      : formatWeekRange(range.from);
  const toConfirm = list.filter((visit) => visit.status === "requested").length;
  const caption =
    view === "day"
      ? `Site visits on ${formatCalendarDate(state.date)}`
      : `Site visits, ${formatWeekRange(range.from)}`;

  return (
    <>
      <LiveRegion message={announcement} />
      <div className="flex flex-wrap items-center justify-between gap-3.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <NavButton
            label={`Previous ${unit}`}
            direction="back"
            onClick={() => go({ date: addDays(state.date, -step), visit: "" })}
          />
          <NavButton
            label={`Next ${unit}`}
            direction="forward"
            onClick={() => go({ date: addDays(state.date, step), visit: "" })}
          />
          <button
            type="button"
            onClick={() => go({ date: istToday(), visit: "" })}
            className="min-h-11 rounded-tile border border-line-strong bg-noir-800 px-3.5 text-caption font-bold text-ivory"
          >
            Today
          </button>
          <h2 className="mx-1 text-lg font-bold" aria-live="polite">
            {heading}
          </h2>
          {visits.data ? (
            <span className="text-caption text-muted">
              {list.length} {list.length === 1 ? "visit" : "visits"} · {toConfirm} to confirm
            </span>
          ) : null}
        </div>
        <SegmentedControl<View>
          label="View"
          value={view}
          options={[
            { value: "week", label: "Week" },
            { value: "day", label: "Day" },
            { value: "list", label: "List" },
          ]}
          onChange={(next) => go({ view: next })}
        />
      </div>

      <form
        aria-label="Filter site visits"
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => event.preventDefault()}
      >
        <Select
          label="Status"
          value={shown.status || (shown.open ? `open:${shown.open}` : "")}
          placeholder="Any status"
          options={[
            { value: "open:true", label: "Still open (to confirm or confirmed)" },
            { value: "open:false", label: "Closed (done, no-show or cancelled)" },
            ...(Object.keys(VISIT_STATUS_SHORT) as VisitStatus[]).map((status) => ({
              value: status,
              label: VISIT_STATUS_SHORT[status],
            })),
          ]}
          onChange={(event) => {
            const value = event.target.value;
            // WHY one list: "still open" is the dashboard's `open=true`, a group of statuses.
            if (value.startsWith("open:")) {
              go({ status: "", open: value === "open:true" ? "true" : "false", visit: "" });
            } else {
              go({ status: value as VisitStatus | "", open: "", visit: "" });
            }
          }}
          className="flex-[1_1_160px] sm:max-w-60"
        />
        <Select
          label="Project"
          value={shown.project_id}
          placeholder="All projects"
          options={projects}
          onChange={(event) => go({ project_id: event.target.value, visit: "" })}
          className="flex-[1_1_200px] sm:max-w-72"
        />
      </form>

      <p className="rounded-tile border border-line bg-noir-800 px-3.5 py-2.5 text-caption">
        <strong className="text-ivory">
          Buyers request a day and a time of day. Confirm the exact time by phone, then record it
          here.
        </strong>{" "}
        All times are India time (IST).
      </p>

      <div className="flex flex-wrap items-start gap-5">
        <section
          aria-label="Visits"
          className="min-w-0 flex-[999_1_620px]"
          aria-busy={visits.loading || undefined}
        >
          {visits.error ? (
            <ErrorPanel
              message={problemMessage(visits.error, "Couldn't load the site visits.")}
              onRetry={visits.reload}
            />
          ) : !visits.data ? (
            <LoadingPanel label="Loading site visits…" rows={5} />
          ) : view === "week" ? (
            <WeekView
              key={pathname}
              monday={range.from}
              visits={list}
              selectedId={state.visit || null}
              onSelect={select}
              caption={caption}
            />
          ) : view === "day" ? (
            <DayView
              day={state.date}
              visits={list}
              selectedId={state.visit || null}
              onSelect={select}
            />
          ) : (
            <ListView
              visits={list}
              selectedId={state.visit || null}
              onSelect={select}
              caption={caption}
            />
          )}
        </section>

        <aside
          aria-labelledby="selected-visit"
          className="flex min-w-0 flex-[1_1_320px] flex-col gap-3.5 rounded-card border border-gold-line-strong bg-noir-800 p-5 lg:max-w-90"
        >
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-bold tracking-[0.08em] text-muted uppercase">
              Site visit
            </span>
            <h2 id="selected-visit" ref={panelHeading} tabIndex={-1} className="text-xl font-bold">
              {selected ? selected.lead_name : "No visit selected"}
            </h2>
            {selected ? (
              <span className="text-caption text-muted tabular-nums">
                {maskPhone(selected.lead_phone_e164)} · ref {selected.lead_reference}
              </span>
            ) : null}
          </div>
          {selected ? (
            <VisitEditor
              key={selected.id}
              visit={selected}
              staff={staff}
              canManage={can("site_visits.manage")}
              idPrefix="calendar-visit"
              onSaved={() => void visits.refresh().catch(() => undefined)}
              onAnnounce={setAnnouncement}
              onDirtyChange={setPanelDirty}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  href={leadPath(selected.lead_id)}
                  className="inline-flex min-h-11 flex-1 items-center justify-center rounded-pill border border-gold-500 px-4 text-small font-bold text-gold-300"
                >
                  Open lead<span className="sr-only"> {selected.lead_reference}</span>
                </Link>
                <ContactLinks phone={selected.lead_phone_e164} name={selected.lead_name} compact />
              </div>
            </VisitEditor>
          ) : (
            <p className="text-small">
              Choose a visit in the calendar to confirm its time, reschedule it or record how it
              went.
            </p>
          )}
        </aside>
      </div>
      {leaveDialog}
    </>
  );
}

function NavButton({
  label,
  direction,
  onClick,
}: {
  label: string;
  direction: "back" | "forward";
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="flex size-11 items-center justify-center rounded-tile border border-line-strong bg-noir-800"
    >
      <svg
        aria-hidden="true"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        className="text-gold-400"
      >
        <path d={direction === "back" ? "M15 6l-6 6 6 6" : "M9 6l6 6-6 6"} />
      </svg>
    </button>
  );
}

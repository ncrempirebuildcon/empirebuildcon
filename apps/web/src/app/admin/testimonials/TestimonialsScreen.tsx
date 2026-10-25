"use client";
/**
 * /admin/testimonials (board NoirCmsContent, "Testimonials"): real buyers' words only. Each one
 * records where it came from and when the person agreed to publishing; "Show on website" stays
 * locked until both are recorded (the API's rule, also a database CHECK).
 *
 * The chosen testimonial and the page of the list live in the address
 * (`?testimonial=<id>|new&page=`); the list is paged (25 a page; review L10). It is empty
 * until real ones are added: the seed adds none, so the website's section stays hidden (honest
 * empty state, AGENTS.md "Honest content").
 *
 * Permissions: reading needs `content.read`; adding, editing, showing and deleting need
 * `content.publish` (the design contract's rule). The API checks both again.
 */
import { useCallback, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Alert, Button, Chip, Switch } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatCalendarDate } from "@/lib/dates";
import { problemMessage } from "@/lib/problems";
import { TESTIMONIALS_PATH } from "@/lib/routes";
import { ContentHeader } from "@/components/admin/content/ContentNav";
import { Pager, pageFrom } from "@/components/admin/Pager";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { useAdminSession } from "../session-context";
import { TestimonialEditor } from "./TestimonialEditor";

type Testimonial = Schema<"Testimonial">;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const PER_PAGE = 25;

function hrefFor(selected: string | null, page = 1): string {
  const search = new URLSearchParams();
  if (page > 1) search.set("page", String(page));
  if (selected) search.set("testimonial", selected);
  const query = search.toString();
  return query ? `${TESTIMONIALS_PATH}?${query}` : TESTIMONIALS_PATH;
}

export function TestimonialsScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const { can } = useAdminSession();
  const canWrite = can("content.publish");
  const raw = params.get("testimonial") ?? "";
  const selected = raw === "new" || UUID_RE.test(raw) ? raw : null;
  const page = pageFrom(params.get("page"));
  const [notice, setNotice] = useState<string | null>(null);
  // The testimonial just saved: a new one sorts onto page 1, but stays open in the editor.
  const [lastSaved, setLastSaved] = useState<Testimonial | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const parts = useDirtyParts();
  const { report } = parts;
  const onDirtyChange = useCallback((dirty: boolean) => report("testimonial", dirty), [report]);
  const { dialog, leave } = useUnsavedChanges(parts.dirty);

  const list = useLoad(`testimonials:${page}`, () =>
    call(
      api.GET("/api/v1/admin/testimonials", {
        params: { query: { page, per_page: PER_PAGE } },
      }),
    ),
  );
  const items = list.data?.items ?? [];
  const current =
    selected && selected !== "new"
      ? (items.find((t) => t.id === selected) ??
        (lastSaved?.id === selected ? lastSaved : undefined))
      : undefined;

  const select = (id: string | null) => {
    setNotice(null);
    leave(hrefFor(id, page), { replace: true });
  };

  async function toggle(item: Testimonial, visible: boolean) {
    setToggling(item.id);
    setToggleError(null);
    try {
      await call(
        api.PATCH("/api/v1/admin/testimonials/{id}", {
          params: { path: { id: item.id } },
          body: { is_visible: visible },
        }),
      );
      await list.refresh();
      setNotice(
        `${item.person_name}'s testimonial is ${visible ? "shown on" : "hidden from"} the website.`,
      );
    } catch (err) {
      setToggleError(problemMessage(err, "Couldn't change whether it is shown."));
    } finally {
      setToggling(null);
    }
  }

  return (
    <>
      <ContentHeader
        current="testimonials"
        description="What buyers said about Empire, shown on the website only with their permission."
        action={
          canWrite ? (
            <Button onClick={() => select("new")} disabled={selected === "new"}>
              + Add testimonial
            </Button>
          ) : null
        }
      />
      <div
        role="note"
        className="flex flex-col gap-1 rounded-tile border border-gold-line-strong bg-gold-tint px-4 py-3 text-small text-gold-300"
      >
        <strong>
          Real testimonials only — record where it came from and when the person agreed.
        </strong>
        <span>
          Use the buyer&apos;s exact words and the name they agreed to. Showing one on the website
          stays locked until its source and consent date are recorded.
        </span>
      </div>
      {notice ? <Alert tone="success">{notice}</Alert> : null}
      {toggleError ? <Alert tone="error">{toggleError}</Alert> : null}
      <div className="flex flex-wrap items-start gap-5">
        <section
          aria-labelledby="testimonials-title"
          className="flex min-w-0 flex-[2_1_440px] flex-col gap-3 rounded-card border border-line bg-noir-800 p-4"
        >
          <h2 id="testimonials-title" className="text-[17px] font-bold">
            Testimonials
          </h2>
          {list.error ? (
            <ErrorPanel
              message={problemMessage(list.error, "Couldn't load testimonials.")}
              onRetry={list.reload}
            />
          ) : !list.data ? (
            <LoadingPanel label="Loading testimonials…" rows={3} />
          ) : list.data.meta.total === 0 ? (
            <EmptyState title="No testimonials yet">
              <p className="max-w-[48ch] text-small">
                Add only real ones, with the buyer&apos;s written permission and a source. The
                Testimonials section on the website stays hidden until at least one is shown.
              </p>
            </EmptyState>
          ) : (
            <>
              <ul className="flex flex-col gap-2">
                {items.map((item) => (
                  <li
                    key={item.id}
                    className={`flex flex-col gap-2 rounded-tile border px-3.5 py-3 ${item.id === selected ? "border-gold-500 bg-gold-tint" : "border-line bg-noir-900"}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <strong className="text-ivory">{item.person_name}</strong>
                      {item.project_name ? (
                        <span className="text-caption text-muted">· {item.project_name}</span>
                      ) : null}
                      <Chip variant={item.is_visible ? "published" : "draft"}>
                        {item.is_visible ? "Shown" : "Not shown"}
                      </Chip>
                    </div>
                    <p className="line-clamp-2 text-small">“{item.quote}”</p>
                    <p className="text-caption text-muted">
                      Source: {item.source} ·{" "}
                      {item.consent_date
                        ? `agreed ${formatCalendarDate(item.consent_date)}`
                        : "consent date not recorded"}
                      {item.rating ? ` · rated ${item.rating} of 5` : ""}
                    </p>
                    <div className="flex flex-wrap items-center gap-3">
                      {canWrite ? (
                        <>
                          <Switch
                            checked={item.is_visible}
                            disabled={!item.can_show && !item.is_visible}
                            busy={toggling === item.id}
                            onChange={(visible) => void toggle(item, visible)}
                            label="Show on website"
                            stateText={{ on: "Shown", off: "Hidden" }}
                            context={item.person_name}
                            aria-describedby={
                              !item.can_show ? `testimonial-locked-${item.id}` : undefined
                            }
                          />
                          <Button
                            variant="secondary"
                            aria-label={`Edit ${item.person_name}'s testimonial`}
                            onClick={() => select(item.id)}
                          >
                            Edit
                          </Button>
                        </>
                      ) : null}
                    </div>
                    {!item.can_show ? (
                      <p id={`testimonial-locked-${item.id}`} className="text-caption text-danger">
                        Locked: record the consent date before showing it.
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
              <Pager
                page={list.data.meta.page}
                perPage={list.data.meta.per_page}
                total={list.data.meta.total}
                pages={list.data.meta.pages}
                hrefFor={(next) => hrefFor(null, next)}
                noun="testimonials"
                singular="testimonial"
              />
            </>
          )}
        </section>
        {canWrite && (selected === "new" || current) ? (
          <TestimonialEditor
            key={selected ?? "none"}
            testimonial={current ?? null}
            onDirtyChange={onDirtyChange}
            onSaved={async (saved, message) => {
              await list.refresh().catch(() => undefined);
              setLastSaved(saved ?? null);
              setNotice(message);
              // WHY not leave(): see OffersScreen; the editor's "saved" report arrives a render later.
              router.replace(hrefFor(saved?.id ?? null, page), { scroll: false });
            }}
            onClose={() => select(null)}
          />
        ) : canWrite && selected && list.data ? (
          <Alert tone="info" title="This testimonial isn't in the list.">
            It may be on another page of the list, or it was deleted.
          </Alert>
        ) : null}
      </div>
      {dialog}
    </>
  );
}

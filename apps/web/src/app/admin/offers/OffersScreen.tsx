"use client";
/**
 * /admin/offers (board NoirCmsContent, "Offers"): every offer with its project, dates, state and
 * placement, and the editor beside it. The chosen offer, the state filter and the page of the list
 * live in the address (`?offer=<id>|new&state=&page=`), so a reload or a shared link opens the
 * same offer. The list is paged (25 a page; review L10).
 *
 * Offers start and end on their own dates (the schedule tick, ARCHITECTURE §10). Ended offers stay
 * for the record; an offer that was never live can be deleted.
 * COMPLIANCE (AGENTS.md "No fake urgency"): there is no countdown field anywhere; the guidance
 * line says so, and the wording checks run before saving (offerForm.ts) and in the API.
 * SECURITY: the screen needs `offers.manage`; the API checks it on every call.
 */
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, Button, Chip, Select, Table, type TableColumn } from "@empire/ui";
import { api, call } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import {
  OFFER_PLACEMENT,
  OFFER_STATE,
  OFFER_STATE_CHIP,
  type OfferState,
} from "@/lib/content/labels";
import { keyOf, optionsOf } from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import { OFFERS_PATH } from "@/lib/routes";
import { ContentHeader } from "@/components/admin/content/ContentNav";
import { Pager, pageFrom } from "@/components/admin/Pager";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { useAdminSession } from "../session-context";
import { OfferEditor } from "./OfferEditor";
import type { Offer } from "./offerForm";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const PER_PAGE = 25;

function hrefFor(selected: string | null, state: OfferState | "", page = 1): string {
  const search = new URLSearchParams();
  if (state) search.set("state", state);
  if (page > 1) search.set("page", String(page));
  if (selected) search.set("offer", selected);
  const query = search.toString();
  return query ? `${OFFERS_PATH}?${query}` : OFFERS_PATH;
}

export function OffersScreen() {
  const params = useSearchParams();
  const { can } = useAdminSession();
  const state = keyOf(OFFER_STATE, params.get("state") ?? "", "" as const);
  const rawOffer = params.get("offer") ?? "";
  const selected = rawOffer === "new" || UUID_RE.test(rawOffer) ? rawOffer : null;
  const page = pageFrom(params.get("page"));
  const [notice, setNotice] = useState<string | null>(null);
  // The offer just saved: a new one may sort onto another page, but stays open in the editor.
  const [lastSaved, setLastSaved] = useState<Offer | null>(null);
  const parts = useDirtyParts();
  const { report } = parts;
  const onDirtyChange = useCallback((dirty: boolean) => report("offer", dirty), [report]);
  const { dialog, leave } = useUnsavedChanges(parts.dirty);

  const list = useLoad(`offers:${state}:${page}`, () =>
    call(
      api.GET("/api/v1/admin/offers", {
        params: { query: { page, per_page: PER_PAGE, state: state || undefined } },
      }),
    ),
  );
  const offers = useMemo(() => list.data?.items ?? [], [list.data]);
  const current =
    selected && selected !== "new"
      ? (offers.find((o) => o.id === selected) ??
        (lastSaved?.id === selected ? lastSaved : undefined))
      : undefined;

  const select = (id: string | null) => {
    setNotice(null);
    leave(hrefFor(id, state, page), { replace: true });
  };

  const columns: TableColumn<Offer>[] = [
    {
      key: "title",
      header: "Offer",
      rowHeader: true,
      cell: (offer) => (
        <span className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-pressed={offer.id === selected}
            onClick={() => select(offer.id)}
            className="min-h-11 text-left font-semibold text-ivory underline-offset-4 hover:underline"
          >
            {offer.title}
          </button>
          {offer.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
        </span>
      ),
    },
    { key: "project", header: "Project", cell: (offer) => offer.project_name ?? "All projects" },
    {
      key: "start",
      header: "Start",
      className: "whitespace-nowrap",
      cell: (offer) => (offer.starts_at ? formatDateTime(offer.starts_at) : "Straight away"),
    },
    {
      key: "end",
      header: "End",
      className: "whitespace-nowrap",
      cell: (offer) => (offer.ends_at ? formatDateTime(offer.ends_at) : "No end date"),
    },
    {
      key: "state",
      header: "Status",
      cell: (offer) => (
        <Chip variant={OFFER_STATE_CHIP[offer.state]}>{OFFER_STATE[offer.state]}</Chip>
      ),
    },
    { key: "placement", header: "Shown on", cell: (offer) => OFFER_PLACEMENT[offer.placement] },
  ];

  return (
    <>
      <ContentHeader
        current="offers"
        description="Offers shown on the website. They go live and end on their own dates; ended offers stay here for the record."
        action={
          can("offers.manage") ? (
            <Button onClick={() => select("new")} disabled={selected === "new"}>
              + New offer
            </Button>
          ) : null
        }
      />
      {notice ? <Alert tone="success">{notice}</Alert> : null}
      <div className="flex flex-wrap items-start gap-5">
        <section
          aria-labelledby="offers-title"
          className="flex min-w-0 flex-[2_1_520px] flex-col gap-3 rounded-card border border-line bg-noir-800 p-4"
        >
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="offers-title" className="text-[17px] font-bold">
                All offers
              </h2>
              <p className="text-caption text-muted">Select an offer to edit it.</p>
            </div>
            <Select
              label="Status"
              value={state}
              placeholder="Any status"
              options={optionsOf(OFFER_STATE)}
              onChange={(event) =>
                leave(hrefFor(selected, keyOf(OFFER_STATE, event.target.value, "")), {
                  replace: true,
                })
              }
              className="min-w-44"
            />
          </div>
          {list.error ? (
            <ErrorPanel
              message={problemMessage(list.error, "Couldn't load offers.")}
              onRetry={list.reload}
            />
          ) : !list.data ? (
            <LoadingPanel label="Loading offers…" rows={4} />
          ) : (
            <>
              <Table
                caption="Offers"
                captionHidden
                columns={columns}
                rows={offers}
                rowKey={(offer) => offer.id}
                minWidth={760}
                busy={list.loading}
                rowClassName={(offer) => (offer.id === selected ? "bg-gold-tint" : undefined)}
                empty={
                  <EmptyState title={state ? "No offers with this status." : "No offers yet."}>
                    <p className="text-small">Add one with + New offer.</p>
                  </EmptyState>
                }
              />
              <Pager
                page={list.data.meta.page}
                perPage={list.data.meta.per_page}
                total={list.data.meta.total}
                pages={list.data.meta.pages}
                hrefFor={(next) => hrefFor(null, state, next)}
                noun="offers"
                singular="offer"
              />
            </>
          )}
        </section>
        {selected === "new" || current ? (
          <OfferEditor
            key={selected ?? "none"}
            offer={current ?? null}
            onDirtyChange={onDirtyChange}
            onSaved={async (saved, message) => {
              setLastSaved(saved ?? null);
              setNotice(message);
              // WHY first, and with history.replaceState: the address must name the saved offer
              // at once. Before (task 5.8 fix), it changed only after the list had reloaded, and
              // a filter changed in between built its address from the stale "new" selection.
              // Next.js keeps useSearchParams in step with history.replaceState. WHY not leave():
              // the editor's "no unsaved changes" report reaches this screen only on the next
              // render, so leave() would still ask.
              window.history.replaceState(null, "", hrefFor(saved?.id ?? null, state, page));
              await list.refresh().catch(() => undefined);
            }}
            onClose={() => select(null)}
          />
        ) : selected && list.data ? (
          <Alert tone="info" title="This offer isn't in the list.">
            It may be on another page, have a different status than the filter shows, or have been
            deleted.
          </Alert>
        ) : null}
      </div>
      {dialog}
    </>
  );
}

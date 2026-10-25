"use client";
/**
 * The media library (/admin/media): every uploaded photo, video and document, as a grid or a
 * list. Search, type, "not attached" and the view live in the address
 * (`?q=&kind=&unattached=true&view=list&page=`), so a filtered view can be shared or reloaded.
 *
 * Each item can be renamed and given alt text and an honest label (the same "details" dialog as
 * the project editor). "Delete from library" is offered only with `media.manage` and only for
 * files attached to nothing ("Used in N places" lists the others); the API refuses
 * anything else (409, also for a project's share image) and deletes the file from the store
 * afterwards (`media.removed`).
 *
 * SECURITY: viewing and editing need `media.upload`, deleting `media.manage` (ARCHITECTURE §11);
 * the API checks both on every call. Hiding a button is never the protection.
 */
import Link from "next/link";
import {
  useMemo,
  useOptimistic,
  useState,
  useTransition,
  type FormEvent,
  type ReactNode,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Alert,
  Button,
  Checkbox,
  Chip,
  ConfirmDialog,
  LiveRegion,
  SegmentedControl,
  Select,
  Table,
  TextField,
  type TableColumn,
} from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { keyOf } from "@/lib/labels";
import { formatBytes, type MediaKind } from "@/lib/media/files";
import { HONEST_LABEL_TONE, honestLabelText } from "@/lib/media/labels";
import type { Media } from "@/lib/media/upload";
import { problemMessage } from "@/lib/problems";
import {
  MEDIA_PATH,
  OFFERS_PATH,
  TESTIMONIALS_PATH,
  pagePath,
  postPath,
  projectPath,
} from "@/lib/routes";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { MediaDetailsDialog } from "@/components/admin/media/MediaDetailsDialog";
import { MediaThumb } from "@/components/admin/media/MediaThumb";
import { Pager } from "@/components/admin/Pager";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../session-context";

const PER_PAGE = 24;

const KIND_LABEL: Record<MediaKind, string> = {
  image: "Photos",
  video: "Videos",
  document: "Documents",
};
const KIND_SINGULAR: Record<MediaKind, string> = {
  image: "Photo",
  video: "Video",
  document: "Document",
};

type View = "grid" | "list";

interface Filters {
  q: string;
  kind: MediaKind | "";
  unattached: boolean;
  view: View;
  page: number;
}

function readFilters(params: URLSearchParams): Filters {
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    q: (params.get("q") ?? "").slice(0, 100),
    kind: keyOf(KIND_LABEL, params.get("kind") ?? "", ""),
    unattached: params.get("unattached") === "true",
    view: params.get("view") === "list" ? "list" : "grid",
    page: Number.isFinite(page) && page > 0 ? page : 1,
  };
}

/** The library address for some filters; defaults are left out. */
function libraryHref(filters: Filters): string {
  const search = new URLSearchParams();
  if (filters.q) search.set("q", filters.q);
  if (filters.kind) search.set("kind", filters.kind);
  if (filters.unattached) search.set("unattached", "true");
  if (filters.view === "list") search.set("view", "list");
  if (filters.page > 1) search.set("page", String(filters.page));
  const query = search.toString();
  return query ? `${MEDIA_PATH}?${query}` : MEDIA_PATH;
}

export function MediaLibrary() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { can } = useAdminSession();
  const canView = can("media.upload");
  const canDelete = can("media.manage");
  const filters = useMemo(() => readFilters(params), [params]);
  const [editing, setEditing] = useState<Media | null>(null);
  const [deleting, setDeleting] = useState<Media | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const hasFilters = Boolean(filters.q || filters.kind || filters.unattached);

  const list = useLoad(libraryHref({ ...filters, view: "grid" }), () =>
    canView
      ? call(
          api.GET("/api/v1/admin/media", {
            params: {
              query: {
                page: filters.page,
                per_page: PER_PAGE,
                q: filters.q || undefined,
                kind: filters.kind || undefined,
                unattached: filters.unattached || undefined,
              },
            },
          }),
        )
      : Promise.reject(new Error("forbidden")),
  );

  // WHY optimistic: the filters live in the address, so a control would snap back until the new
  // address arrives; `shown` shows the user's choice straight away (React 19 useOptimistic).
  const [, startTransition] = useTransition();
  const [shown, setShown] = useOptimistic(filters, (current: Filters, next: Filters) => next);
  function apply(next: Partial<Filters>) {
    const target = { ...filters, page: 1, ...next };
    startTransition(() => {
      setShown(target);
      router.replace(libraryHref(target), { scroll: false });
    });
  }

  async function confirmDelete() {
    if (!deleting || deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await call(api.DELETE("/api/v1/admin/media/{id}", { params: { path: { id: deleting.id } } }));
    } catch (err) {
      setDeleteError(problemMessage(err, "Couldn't delete the file."));
      setDeleteBusy(false);
      return;
    }
    setMessage(`${deleting.title} was deleted from the library.`);
    setDeleting(null);
    setDeleteBusy(false);
    await list.refresh().catch(() => undefined);
    // WHY: the deleted item's buttons are gone; return focus to a stable place.
    requestAnimationFrame(() => document.getElementById("media-search")?.focus());
  }

  if (!canView) {
    return (
      <Alert tone="info">
        Your role can&apos;t open the media library. Ask an admin if you need it.
      </Alert>
    );
  }

  const items = list.data?.items ?? [];
  const actions = (media: Media) => (
    <ItemActions
      media={media}
      canDelete={canDelete}
      onEdit={() => setEditing(media)}
      onDelete={() => {
        setDeleteError(null);
        setDeleting(media);
      }}
    />
  );

  return (
    <>
      <p className="max-w-[70ch] text-small text-muted">
        Every photo, video and document uploaded to the CMS. Files are added and arranged on each
        project; here you can rename them, add alt text and honest labels, and delete files that
        nothing uses any more.
      </p>

      <FilterBar
        key={pathname + filters.q}
        filters={shown}
        onApply={apply}
        clearHref={
          hasFilters ? libraryHref({ ...filters, q: "", kind: "", unattached: false }) : null
        }
      />

      {list.error ? (
        <ErrorPanel
          message={problemMessage(list.error, "Couldn't load the media library.")}
          onRetry={list.reload}
        />
      ) : !list.data ? (
        <LoadingPanel label="Loading the media library…" rows={6} />
      ) : (
        <>
          <section
            aria-label="Media files"
            aria-busy={list.loading || undefined}
            className="flex flex-col gap-3"
          >
            {items.length === 0 ? (
              <div className="rounded-card border border-line bg-noir-800">
                {hasFilters ? (
                  <EmptyState title="No files match these filters.">
                    <Link href={MEDIA_PATH} className="font-bold underline">
                      Clear filters
                    </Link>
                  </EmptyState>
                ) : (
                  <EmptyState title="No media yet.">
                    <p className="text-small">
                      Upload photos, videos and documents in a project&apos;s Media tab.
                    </p>
                  </EmptyState>
                )}
              </div>
            ) : filters.view === "grid" ? (
              <LibraryGrid items={items} actions={actions} />
            ) : (
              <div className="overflow-hidden rounded-card border border-line bg-noir-800">
                <Table
                  caption="Media files"
                  captionHidden
                  columns={listColumns(actions)}
                  rows={items}
                  rowKey={(row) => row.id}
                  minWidth={860}
                  busy={list.loading}
                />
              </div>
            )}
          </section>
          <Pager
            page={list.data.meta.page}
            perPage={list.data.meta.per_page}
            total={list.data.meta.total}
            pages={list.data.meta.pages}
            hrefFor={(page) => libraryHref({ ...filters, page })}
            noun="files"
            singular="file"
          />
        </>
      )}

      <MediaDetailsDialog
        media={editing}
        onClose={() => setEditing(null)}
        onSaved={async (saved) => {
          setMessage(`Details of ${saved.title} were saved.`);
          await list.refresh().catch(() => undefined);
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        title={deleting ? `Delete ${deleting.title} from the library?` : ""}
        confirmLabel="Delete from library"
        tone="danger"
        busy={deleteBusy}
        error={deleteError}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
      >
        The file is deleted from the library and from the file store for good. This can&apos;t be
        undone.
      </ConfirmDialog>
      <LiveRegion message={message} />
    </>
  );
}

function LibraryGrid({
  items,
  actions,
}: {
  items: readonly Media[];
  actions: (media: Media) => ReactNode;
}) {
  return (
    <ul
      aria-label="Media files"
      className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,200px),1fr))] gap-3.5"
    >
      {items.map((media) => (
        <li
          key={media.id}
          className="flex min-w-0 flex-col overflow-hidden rounded-tile border border-line bg-noir-900"
        >
          <MediaThumb media={media} shape={media.kind === "video" ? "video" : "photo"} />
          <div className="flex flex-1 flex-col gap-1.5 p-2.5">
            <h2 className="text-small font-bold text-ivory [overflow-wrap:anywhere]">
              {media.title}
            </h2>
            {media.is_sample ? (
              <Chip variant="sample" className="self-start">
                SAMPLE
              </Chip>
            ) : null}
            <LabelLine media={media} />
            <span className="text-xs text-muted">{metaOf(media)}</span>
            <UsesLine media={media} />
            <div className="mt-auto pt-1">{actions(media)}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function listColumns(actions: (media: Media) => ReactNode): TableColumn<Media>[] {
  return [
    {
      key: "preview",
      header: "Preview",
      headerHidden: true,
      className: "w-24",
      cell: (row) => (
        <MediaThumb
          media={row}
          shape={row.kind === "video" ? "video" : "photo"}
          className="w-20 rounded-tag"
        />
      ),
    },
    {
      key: "title",
      header: "Title",
      rowHeader: true,
      cell: (row) => (
        <span className="flex flex-col gap-0.5">
          <span className="text-ivory [overflow-wrap:anywhere]">{row.title}</span>
          {row.is_sample ? (
            <Chip variant="sample" className="self-start">
              SAMPLE
            </Chip>
          ) : null}
          <LabelLine media={row} />
        </span>
      ),
    },
    {
      key: "kind",
      header: "Type",
      className: "whitespace-nowrap",
      cell: (row) => `${KIND_SINGULAR[row.kind]} · ${row.format.toUpperCase()}`,
    },
    {
      key: "size",
      header: "Size",
      className: "whitespace-nowrap tabular-nums",
      cell: (row) => formatBytes(row.bytes),
    },
    {
      key: "uses",
      header: "Used on",
      cell: (row) => <UsesLine media={row} />,
    },
    {
      key: "uploaded",
      header: "Uploaded",
      className: "whitespace-nowrap text-muted",
      cell: (row) => (row.created_at ? formatDateTime(row.created_at) : "—"),
    },
    {
      key: "actions",
      header: "Actions",
      headerHidden: true,
      className: "whitespace-nowrap",
      cell: (row) => actions(row),
    },
  ];
}

/**
 * The honest label of an image, or a neutral "No label". WHY not the red warning: the library also
 * holds QR codes, floor plans and share images that need no label; the warning belongs to the
 * photo lists, where an unlabelled photo stays hidden.
 */
function LabelLine({ media }: { media: Media }) {
  if (media.kind !== "image") return null;
  const text = honestLabelText(media.label, media.label_month);
  return text && media.label ? (
    <span className={`text-caption font-bold ${HONEST_LABEL_TONE[media.label]}`}>{text}</span>
  ) : (
    <span className="text-caption text-muted">No label</span>
  );
}

/**
 * "Not attached to anything", or "Used in N places" that opens (native <details>) to list them
 * from `GET /admin/media/{id}/usage`: projects, pages, posts, offers and testimonials, each a link
 * to where it is used (spec Phase 4 part 4 §10), so staff know what to change before deleting.
 */
function UsesLine({ media }: { media: Media }) {
  const uses = media.attached_count;
  const [open, setOpen] = useState(false);
  if (uses === 0) return <span className="text-xs text-muted">Not attached to anything</span>;
  return (
    <details
      className="text-xs text-muted"
      onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="inline-flex min-h-11 cursor-pointer items-center font-semibold text-gold-400">
        Used in {uses} {uses === 1 ? "place" : "places"}
      </summary>
      {open ? <UsageList mediaId={media.id} /> : null}
    </details>
  );
}

const USE_ROLE: Record<string, string> = {
  gallery: "photo",
  floor_plan: "floor plan",
  brochure: "brochure",
  rera_qr: "RERA QR code",
  video: "video",
  document: "document",
  share_image: "share image",
  block: "in a block",
  cover: "cover",
  image: "image",
  photo: "photo",
};

function hrefOfUse(use: Schema<"MediaUse">): string | null {
  switch (use.owner_type) {
    case "project":
    case "configuration":
    case "construction_update":
      return use.project_id ? projectPath(use.project_id) : null;
    case "page":
      return pagePath(use.owner_id);
    case "post":
      return postPath(use.owner_id);
    case "offer":
      return `${OFFERS_PATH}?offer=${use.owner_id}`;
    case "testimonial":
      return `${TESTIMONIALS_PATH}?testimonial=${use.owner_id}`;
  }
}

function UsageList({ mediaId }: { mediaId: string }) {
  const usage = useLoad(`media-usage:${mediaId}`, () =>
    call(api.GET("/api/v1/admin/media/{id}/usage", { params: { path: { id: mediaId } } })),
  );
  if (usage.error) {
    return (
      <p className="text-danger">
        {problemMessage(usage.error, "Couldn't load where it is used.")}
      </p>
    );
  }
  if (!usage.data) return <p role="status">Loading…</p>;
  return (
    <ul className="mt-1 flex flex-col gap-1">
      {usage.data.map((use) => {
        const href = hrefOfUse(use);
        // WHY: a testimonial's name already says "Testimonial photo (R. K. S.)" (initials only,
        // never the buyer's name; review L9), so its role isn't repeated.
        const text =
          use.owner_type === "testimonial"
            ? use.name
            : `${use.name} (${USE_ROLE[use.role] ?? use.role})`;
        return (
          <li key={`${use.owner_type}:${use.owner_id}:${use.role}`}>
            {href ? (
              <Link href={href} className="underline underline-offset-2">
                {text}
              </Link>
            ) : (
              text
            )}
          </li>
        );
      })}
    </ul>
  );
}

function ItemActions({
  media,
  canDelete,
  onEdit,
  onDelete,
}: {
  media: Media;
  canDelete: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  // INVARIANT (mirrors the API's 409): a file still used somewhere is never offered for
  // deletion; "Used in N places" says where. The API refuses it too (blocks, covers, share
  // images, offer images and testimonial photos count since part 4).
  const unattached = media.attached_count === 0;
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <Button
        variant="secondary"
        className="px-3.5"
        aria-label={`Edit details: ${media.title}`}
        onClick={onEdit}
      >
        Edit details
      </Button>
      {canDelete && unattached ? (
        <Button
          variant="danger"
          className="px-3.5"
          aria-label={`Delete from library: ${media.title}`}
          onClick={onDelete}
        >
          Delete from library
        </Button>
      ) : null}
    </span>
  );
}

function metaOf(media: Media): string {
  const parts = [
    `${KIND_SINGULAR[media.kind]} · ${media.format.toUpperCase()}`,
    formatBytes(media.bytes),
  ];
  if (media.width && media.height) parts.push(`${media.width} × ${media.height}`);
  return parts.join(" · ");
}

function FilterBar({
  filters,
  onApply,
  clearHref,
}: {
  filters: Filters;
  onApply: (next: Partial<Filters>) => void;
  clearHref: string | null;
}) {
  // WHY no effect to sync: the parent re-keys this bar when the address's search changes.
  const [query, setQuery] = useState(filters.q);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply({ q: query.trim() });
  }

  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <form
        role="search"
        aria-label="Filter media"
        onSubmit={onSubmit}
        className="flex flex-[1_1_520px] flex-wrap items-end gap-3"
      >
        <div className="flex min-w-60 flex-[2_1_240px] items-end gap-2">
          <TextField
            id="media-search"
            label="Search"
            type="search"
            name="q"
            placeholder="Title or alt text"
            value={query}
            maxLength={100}
            onChange={(event) => setQuery(event.target.value)}
            className="flex-1"
          />
          <Button type="submit" variant="secondary" className="mb-0.75">
            Search
          </Button>
        </div>
        <Select
          label="Type"
          value={filters.kind}
          placeholder="All types"
          options={(Object.keys(KIND_LABEL) as MediaKind[]).map((kind) => ({
            value: kind,
            label: KIND_LABEL[kind],
          }))}
          onChange={(event) => onApply({ kind: keyOf(KIND_LABEL, event.target.value, "") })}
          className="flex-[1_1_160px]"
        />
        <Checkbox
          className="mb-3 flex-[1_1_200px]"
          checked={filters.unattached}
          onChange={(event) => onApply({ unattached: event.target.checked })}
          label="Only files not attached to anything"
        />
        {clearHref ? (
          <Link
            href={clearHref}
            className="inline-flex min-h-11 items-center px-1 font-bold underline"
          >
            Clear filters
          </Link>
        ) : null}
      </form>
      <SegmentedControl
        label="View"
        value={filters.view}
        onChange={(view) => onApply({ view, page: filters.page })}
        options={[
          { value: "grid", label: "Grid" },
          { value: "list", label: "List" },
        ]}
      />
    </div>
  );
}

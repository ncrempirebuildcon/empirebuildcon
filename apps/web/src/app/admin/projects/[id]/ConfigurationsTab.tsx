"use client";
/**
 * Configurations (board NoirCmsProject, "Configurations"): the table of homes on offer, each a
 * property page on the website. Add, edit, remove and reorder; each change saves straight away.
 *
 * Floor plans (one image or PDF per configuration) are uploaded and replaced in the table's
 * Floor plan column (FloorPlanCell.tsx); they save straight away, like the rest of the media.
 *
 * COMPLIANCE: carpet area is typed in sq ft and stored once in square metres; sq m is shown
 * "auto" with the shared helpers, so the two figures can never disagree (AGENTS.md "Carpet area
 * comes first, in sq ft and sq m"; ARCHITECTURE §6).
 */
import {
  Alert,
  Button,
  Chip,
  LiveRegion,
  ReorderButtons,
  Table,
  formatInr,
  type TableColumn,
} from "@empire/ui";
import { api, call } from "@/lib/api";
import { AREA_BASIS, SALES_STATUS, SALES_STATUS_CHIP } from "@/lib/labels";
import { CollectionForm, DiscardDialog, RemoveDialog } from "@/components/admin/CollectionEditor";
import { EmptyState, Panel } from "@/components/admin/states";
import { useCollection } from "@/components/admin/useCollection";
import { ConfigurationFields } from "./ConfigurationFields";
import { FloorPlanCell } from "./FloorPlanCell";
import {
  emptyDraft,
  sqftRange,
  sqmRange,
  toDraft,
  toInput,
  validate,
  type ConfigurationDraft,
} from "./configurationDraft";
import { useReportDirty, type ChildTabProps, type Configuration } from "./editorTypes";

const STICKY = "sticky left-0 z-[1] min-w-40 bg-noir-800 shadow-[inset_-1px_0_0_var(--color-line)]";

export function ConfigurationsTab({
  project,
  canWrite,
  canUpload,
  onChanged,
  reportDirty,
}: ChildTabProps & { canUpload: boolean }) {
  const id = project.id;
  const towers = project.towers ?? [];
  const configurations = useCollection<Configuration, ConfigurationDraft>({
    items: project.configurations ?? [],
    getId: (c) => c.id,
    getLabel: (c) => c.name,
    emptyDraft,
    toDraft,
    validate,
    create: (d) =>
      call(
        api.POST("/api/v1/admin/projects/{id}/configurations", {
          params: { path: { id } },
          body: toInput(d),
        }),
      ),
    update: (itemId, d) =>
      call(
        api.PATCH("/api/v1/admin/projects/{id}/configurations/{item_id}", {
          params: { path: { id, item_id: itemId } },
          body: toInput(d),
        }),
      ),
    remove: (itemId) =>
      call(
        api.DELETE("/api/v1/admin/projects/{id}/configurations/{item_id}", {
          params: { path: { id, item_id: itemId } },
        }),
      ),
    reorder: (ids) =>
      call(
        api.PUT("/api/v1/admin/projects/{id}/configurations/order", {
          params: { path: { id } },
          body: { ids },
        }),
      ),
    onChanged,
    noun: "configuration",
  });
  useReportDirty("configurations", configurations.dirty, reportDirty);
  const c = configurations;
  const towerName = (towerId: string | null | undefined) =>
    towers.find((t) => t.id === towerId)?.name;

  const columns: TableColumn<Configuration>[] = [
    {
      key: "type",
      header: "Type",
      rowHeader: true,
      // WHY sticky: the table scrolls sideways on narrower screens; the name stays in view.
      className: STICKY,
      headerClassName: STICKY,
      cell: (row) => (
        <span className="flex flex-col">
          <span className="text-ivory">{row.name}</span>
          <span className="text-xs font-medium text-muted">
            {towerName(row.tower_id) ? `${towerName(row.tower_id)} only` : "All towers"}
            {row.is_sample ? " · SAMPLE" : ""}
          </span>
        </span>
      ),
    },
    {
      key: "sqft",
      header: "Carpet (sq ft)",
      className: "tabular-nums whitespace-nowrap",
      cell: (row) => (
        <span className="flex flex-col">
          <span className="text-ivory">{sqftRange(row.area.min_sqm, row.area.max_sqm)}</span>
          {row.area.basis && row.area.basis !== "carpet" ? (
            <span className="text-xs text-muted">{AREA_BASIS[row.area.basis]}</span>
          ) : null}
        </span>
      ),
    },
    {
      key: "sqm",
      header: "Carpet (sq m)",
      className: "tabular-nums whitespace-nowrap",
      cell: (row) => (
        <span className="flex flex-col">
          <strong className="text-ivory">{sqmRange(row.area.min_sqm, row.area.max_sqm)}</strong>
          <span className="text-xs text-muted">auto</span>
        </span>
      ),
    },
    {
      key: "balconies",
      header: "Balconies",
      className: "tabular-nums",
      cell: (row) => (row.balconies != null ? String(row.balconies) : "—"),
    },
    {
      key: "price",
      header: "Price from",
      className: "tabular-nums whitespace-nowrap font-extrabold text-gold-300",
      cell: (row) =>
        row.price.on_request
          ? "On request"
          : row.price.min_inr != null
            ? formatInr(row.price.min_inr)
            : "—",
    },
    {
      key: "plan",
      header: "Floor plan",
      className: "min-w-44",
      cell: (row) => (
        <FloorPlanCell
          configuration={row}
          canUpload={canUpload}
          onChanged={onChanged}
          reportDirty={reportDirty}
        />
      ),
    },
    {
      key: "availability",
      header: "Availability",
      cell: (row) => (
        <Chip variant={SALES_STATUS_CHIP[row.sales_status]}>{SALES_STATUS[row.sales_status]}</Chip>
      ),
    },
    ...(canWrite
      ? [
          {
            key: "actions",
            header: "Order and actions",
            headerHidden: true,
            className: "whitespace-nowrap",
            cell: (row: Configuration, index: number) => (
              <span className="flex gap-2">
                <ReorderButtons
                  index={index}
                  count={c.ordered.length}
                  itemLabel={row.name}
                  onMove={c.move}
                  disabled={c.moving}
                />
                <Button
                  id={`configurations-edit-${row.id}`}
                  variant="secondary"
                  aria-label={`Edit ${row.name}`}
                  onClick={() => c.startEdit(row)}
                >
                  Edit
                </Button>
                <Button
                  variant="danger"
                  aria-label={`Remove ${row.name}`}
                  onClick={() => c.askRemove(row)}
                >
                  Remove
                </Button>
              </span>
            ),
          },
        ]
      : []),
  ];

  const editingRow = c.ordered.find((row) => row.id === c.editingId);

  return (
    <Panel
      id="configurations"
      title="Configurations"
      description="Each one is a property page on the website. Availability is tracked per configuration, not per flat."
      actions={
        canWrite && c.editing !== "new" ? (
          <Button id="configurations-add" onClick={c.startNew}>
            + Add configuration
          </Button>
        ) : null
      }
    >
      {c.listError ? <Alert tone="error">{c.listError}</Alert> : null}
      {c.ordered.length === 0 ? (
        <EmptyState title="No configurations yet.">
          <p className="text-small">Add at least one before the project can be published.</p>
        </EmptyState>
      ) : (
        <div className="-mx-4.5 border-y border-line">
          <Table
            caption="Configurations"
            captionHidden
            columns={columns}
            rows={c.ordered}
            rowKey={(row) => row.id}
            minWidth={980}
          />
        </div>
      )}
      <p className="text-caption text-muted">
        Type the carpet area in sq ft; sq m is worked out for you (× 0.092903). Area is stored once,
        and the website shows carpet area in both units, as registered with RERA. Sold-out
        configurations show after available ones, with a Sold out badge.
      </p>
      {c.draft && (c.editing === "new" || editingRow) ? (
        <CollectionForm
          title={editingRow ? `Edit ${editingRow.name}` : "Add configuration"}
          collection={c}
          returnFocusTo={editingRow ? `configurations-edit-${editingRow.id}` : "configurations-add"}
        >
          <ConfigurationFields collection={c} towers={towers} />
        </CollectionForm>
      ) : null}
      <LiveRegion message={c.message} />
      <DiscardDialog collection={c} />
      <RemoveDialog
        collection={c}
        getLabel={(row) => row.name}
        focusAfterRemove="configurations-add"
      />
    </Panel>
  );
}

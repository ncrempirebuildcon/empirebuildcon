"use client";
/**
 * One catalogue list (cities, localities or amenities): a table with Edit and Delete per row, an
 * "+ Add …" button, and the add/edit form under the table.
 *
 * Delete asks first. When the API refuses because the row is still used (409, e.g. "Used by 2
 * projects"), its message is shown in the dialog, so staff know to change those projects first.
 */
import type { ReactNode } from "react";
import { Alert, Button, LiveRegion, Table, type TableColumn } from "@empire/ui";
import type { FieldErrors } from "@/lib/problems";
import { CollectionForm, DiscardDialog, RemoveDialog } from "@/components/admin/CollectionEditor";
import { EmptyState, Panel } from "@/components/admin/states";
import type { Collection } from "@/components/admin/useCollection";

export interface CatalogueSectionProps<T, D> {
  /** Id prefix, e.g. "cities". */
  id: string;
  title: string;
  description?: ReactNode;
  /** Singular noun for button labels, e.g. "city". */
  noun: string;
  collection: Collection<T, D>;
  columns: TableColumn<T>[];
  getId: (item: T) => string;
  getLabel: (item: T) => string;
  renderForm: (draft: D, setDraft: (patch: Partial<D>) => void, errors: FieldErrors) => ReactNode;
  canWrite: boolean;
  emptyText: string;
  /** Controls above the table, e.g. the localities' city filter. */
  filters?: ReactNode;
  /** What the delete dialog says for one row; a generic sentence when left out. */
  removeBody?: (item: T) => ReactNode;
  loading?: boolean;
}

export function CatalogueSection<T, D>(props: CatalogueSectionProps<T, D>) {
  const { id, collection: c, getId, getLabel, canWrite, noun } = props;
  const columns: TableColumn<T>[] = canWrite
    ? [
        ...props.columns,
        {
          key: "actions",
          header: "Actions",
          headerHidden: true,
          className: "w-0 whitespace-nowrap",
          headerClassName: "w-0",
          cell: (row: T) => (
            <span className="flex gap-2">
              <Button
                id={`${id}-edit-${getId(row)}`}
                variant="secondary"
                aria-label={`Edit ${getLabel(row)}`}
                onClick={() => c.startEdit(row)}
              >
                Edit
              </Button>
              <Button
                variant="danger"
                aria-label={`Delete ${getLabel(row)}`}
                onClick={() => c.askRemove(row)}
              >
                Delete
              </Button>
            </span>
          ),
        },
      ]
    : props.columns;
  const editingRow = c.ordered.find((row) => getId(row) === c.editingId);

  return (
    <Panel
      id={id}
      title={props.title}
      description={props.description}
      actions={
        canWrite && c.editing !== "new" ? (
          <Button id={`${id}-add`} variant="secondary" onClick={c.startNew}>
            + Add {noun}
          </Button>
        ) : null
      }
    >
      {props.filters}
      {c.listError ? <Alert tone="error">{c.listError}</Alert> : null}
      <div className="-mx-4.5 border-y border-line">
        <Table
          caption={props.title}
          captionHidden
          columns={columns}
          rows={c.ordered}
          rowKey={getId}
          busy={props.loading}
          empty={<EmptyState title={props.emptyText} />}
        />
      </div>
      {c.draft && (c.editing === "new" || editingRow) ? (
        <CollectionForm
          title={editingRow ? `Edit ${getLabel(editingRow)}` : `Add ${noun}`}
          collection={c}
          returnFocusTo={editingRow ? `${id}-edit-${getId(editingRow)}` : `${id}-add`}
        >
          {props.renderForm(c.draft, c.setDraft, c.errors)}
        </CollectionForm>
      ) : null}
      <LiveRegion message={c.message} />
      <DiscardDialog collection={c} />
      <RemoveDialog
        collection={c}
        getLabel={getLabel}
        verb="Delete"
        focusAfterRemove={`${id}-add`}
        body={
          c.removing && props.removeBody
            ? props.removeBody(c.removing)
            : `The ${noun} is deleted from the catalogue. A ${noun} that projects still use can't be deleted.`
        }
      />
    </Panel>
  );
}

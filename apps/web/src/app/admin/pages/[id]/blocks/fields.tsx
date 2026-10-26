"use client";
/**
 * Building blocks for the block settings forms: optional text, a button (text + link), an
 * ordered list of items (numbers, steps, columns) with Move up/down and Remove, a picked list of
 * ids (FAQs, testimonials), the project and city choices, and the library items the page uses.
 *
 * Accessibility: every input has a visible label; item groups are fieldsets with a legend
 * ("Number 2"); moves and removals are announced in a polite live region, and the move buttons
 * name the item ("Move Number 2 up"), like every ordered list in the CMS.
 */
import { createContext, useContext, useState, type ReactNode } from "react";
import {
  Button,
  LiveRegion,
  ReorderButtons,
  Select,
  TextField,
  moveAnnouncement,
  moveItem,
  type SelectOption,
} from "@empire/ui";
import { api, call } from "@/lib/api";
import type { Media } from "@/lib/media/upload";
import type { FieldErrors } from "@/lib/problems";
import { useLoad } from "@/components/admin/useLoad";

/** Props every block form gets. */
export interface BlockFormProps<D> {
  data: D;
  onChange: (data: D) => void;
  /** Problems keyed by the path inside `data` ("heading", "items.0.source"). */
  errors: FieldErrors;
  /** Prefix for element ids, unique per block. */
  idPrefix: string;
  /** With `media.upload`: media fields offer an upload button. */
  canUpload: boolean;
  /** Called with true while a file is being sent (for the leave warning). */
  onBusyChange: (busy: boolean) => void;
}

/** "" → null for optional text. */
export const orNull = (value: string) => (value.trim() === "" ? null : value);

/** The optional heading most blocks have. */
export function HeadingField<D extends { heading?: string | null }>({
  data,
  onChange,
  errors,
  idPrefix,
}: Pick<BlockFormProps<D>, "data" | "onChange" | "errors" | "idPrefix">) {
  return (
    <OptionalText
      id={`${idPrefix}-heading`}
      label="Heading"
      maxLength={120}
      value={data.heading}
      onChange={(heading) => onChange({ ...data, heading })}
      error={errors.heading}
    />
  );
}

/** An optional single-line text field (null when empty). */
export function OptionalText({
  label,
  value,
  onChange,
  maxLength,
  error,
  hint,
  id,
}: {
  label: string;
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  maxLength: number;
  error?: string;
  hint?: ReactNode;
  id: string;
}) {
  return (
    <TextField
      id={id}
      label={`${label} (optional)`}
      maxLength={maxLength}
      value={value ?? ""}
      onChange={(event) => onChange(orNull(event.target.value))}
      error={error}
      hint={hint}
    />
  );
}

export interface ButtonValue {
  label: string;
  href: string;
}

/**
 * A button's text and link. With `optional`, both empty means "no button" (null).
 * The link hint says what is allowed; the check itself is in blockDraft.ts (and the API).
 */
export function ButtonFields({
  legend,
  value,
  onChange,
  errors,
  prefix,
  idPrefix,
  optional = false,
}: {
  legend: string;
  value: ButtonValue | null;
  onChange: (value: ButtonValue | null) => void;
  errors: FieldErrors;
  /** The field path of the button inside `data` ("cta"), or "" when it is the block itself. */
  prefix: string;
  idPrefix: string;
  optional?: boolean;
}) {
  const key = (name: string) => (prefix ? `${prefix}.${name}` : name);
  const set = (patch: Partial<ButtonValue>) => {
    const next = { label: value?.label ?? "", href: value?.href ?? "", ...patch };
    onChange(optional && !next.label.trim() && !next.href.trim() ? null : next);
  };
  return (
    <fieldset className="flex min-w-0 flex-col gap-3 rounded-tile border border-line p-3">
      <legend className="px-1 text-small font-semibold text-ivory">
        {legend}
        {optional ? <span className="font-normal text-muted"> (optional)</span> : null}
      </legend>
      <div className="flex flex-wrap gap-3">
        <TextField
          id={`${idPrefix}-${key("label")}`}
          label="Button text"
          maxLength={40}
          value={value?.label ?? ""}
          onChange={(event) => set({ label: event.target.value })}
          error={errors[key("label")]}
          className="min-w-0 flex-[1_1_160px]"
        />
        <TextField
          id={`${idPrefix}-${key("href")}`}
          label="Link"
          maxLength={500}
          value={value?.href ?? ""}
          placeholder="/contact"
          onChange={(event) => set({ href: event.target.value.trim() })}
          error={errors[key("href")]}
          hint="A page on this site (/contact) or a full https:// address."
          className="min-w-0 flex-[2_1_200px]"
        />
      </div>
    </fieldset>
  );
}

/**
 * An ordered list of items (numbers, steps, columns): each item is a fieldset with its fields,
 * Move up/down and Remove; "+ Add" under the list. `min` and `max` follow the API's limits.
 */
export function ItemsEditor<T>({
  items,
  onChange,
  noun,
  min,
  max,
  make,
  render,
  addLabel,
}: {
  items: readonly T[];
  onChange: (items: T[]) => void;
  /** "Number", "Step", "Column": the legend is "Number 2". */
  noun: string;
  min: number;
  max: number;
  make: () => T;
  render: (item: T, index: number, set: (patch: Partial<T>) => void) => ReactNode;
  addLabel: string;
}) {
  const [message, setMessage] = useState("");
  const update = (index: number, patch: Partial<T>) =>
    onChange(items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-3">
        {items.map((item, index) => (
          // WHY index keys: items have no ids; moves re-render the fields with their new values,
          // and focus follows the moved item through the announcement instead.
          <li key={index}>
            <fieldset className="flex min-w-0 flex-col gap-3 rounded-tile border border-line bg-noir-900 p-3">
              <legend className="px-1 text-small font-semibold text-ivory">
                {noun} {index + 1}
              </legend>
              {render(item, index, (patch) => update(index, patch))}
              <div className="flex flex-wrap gap-2">
                <ReorderButtons
                  index={index}
                  count={items.length}
                  itemLabel={`${noun} ${index + 1}`}
                  onMove={(from, to) => {
                    onChange(moveItem(items, from, to));
                    setMessage(moveAnnouncement(`${noun} ${from + 1}`, to, items.length));
                  }}
                />
                {items.length > min ? (
                  <Button
                    variant="tertiary"
                    className="min-h-11"
                    aria-label={`Remove ${noun} ${index + 1}`}
                    onClick={() => {
                      onChange(items.filter((_, i) => i !== index));
                      setMessage(`${noun} ${index + 1} removed.`);
                    }}
                  >
                    Remove
                  </Button>
                ) : null}
              </div>
            </fieldset>
          </li>
        ))}
      </ol>
      {items.length < max ? (
        <Button
          variant="secondary"
          className="self-start"
          onClick={() => {
            onChange([...items, make()]);
            setMessage(`${noun} ${items.length + 1} added.`);
          }}
        >
          {addLabel}
        </Button>
      ) : (
        <p className="text-caption text-muted">That is the most this block takes ({max}).</p>
      )}
      <LiveRegion message={message} />
    </div>
  );
}

/**
 * A picked, ordered list of ids (FAQs, testimonials): Move up/down and Remove on each, and a
 * choice of the ones not yet picked with "Add".
 */
export function IdListPicker({
  label,
  options,
  value,
  onChange,
  max,
  idPrefix,
  error,
  emptyText,
}: {
  label: string;
  options: readonly SelectOption[];
  value: readonly string[];
  onChange: (ids: string[]) => void;
  max: number;
  idPrefix: string;
  error?: string;
  emptyText: string;
}) {
  const [choice, setChoice] = useState("");
  const [message, setMessage] = useState("");
  const labelOf = (id: string) => options.find((o) => o.value === id)?.label ?? "Item not found";
  const remaining = options.filter((option) => !value.includes(option.value));
  return (
    <div role="group" aria-labelledby={`${idPrefix}-label`} className="flex flex-col gap-2">
      <span id={`${idPrefix}-label`} className="text-small font-semibold text-ivory">
        {label} · {value.length} of {max}
      </span>
      {value.length === 0 ? (
        <p className="text-caption text-muted">{emptyText}</p>
      ) : (
        <ol className="flex flex-col gap-2" aria-label={`${label} in order`}>
          {value.map((id, index) => (
            <li
              key={id}
              className="flex flex-wrap items-center gap-2 rounded-tile border border-line bg-noir-900 px-3 py-2"
            >
              <span className="min-w-0 flex-[1_1_160px] text-caption [overflow-wrap:anywhere] text-ivory">
                {labelOf(id)}
              </span>
              <ReorderButtons
                index={index}
                count={value.length}
                itemLabel={labelOf(id)}
                onMove={(from, to) => {
                  onChange(moveItem(value, from, to));
                  setMessage(moveAnnouncement(labelOf(id), to, value.length));
                }}
              />
              <Button
                variant="tertiary"
                className="min-h-11"
                aria-label={`Remove ${labelOf(id)}`}
                onClick={() => {
                  onChange(value.filter((other) => other !== id));
                  setMessage(`${labelOf(id)} removed.`);
                }}
              >
                Remove
              </Button>
            </li>
          ))}
        </ol>
      )}
      {error ? <p className="text-caption text-danger">{error}</p> : null}
      {value.length < max && remaining.length > 0 ? (
        <div className="flex flex-wrap items-end gap-2">
          <Select
            id={`${idPrefix}-choice`}
            label="Add"
            value={choice}
            placeholder="Choose…"
            options={remaining}
            onChange={(event) => setChoice(event.target.value)}
            className="min-w-0 flex-[1_1_220px]"
          />
          <Button
            variant="secondary"
            className="mb-0.75"
            disabled={!choice}
            onClick={() => {
              if (!choice) return;
              onChange([...value, choice]);
              setMessage(`${labelOf(choice)} added.`);
              setChoice("");
            }}
          >
            Add
          </Button>
        </div>
      ) : null}
      <LiveRegion message={message} />
    </div>
  );
}

/** The CMS's projects as choices (name, and SAMPLE for sample projects). */
export function useProjectOptions(): { options: SelectOption[]; loading: boolean } {
  const list = useLoad("block-projects", () =>
    call(api.GET("/api/v1/admin/projects", { params: { query: { per_page: 100 } } })),
  );
  return {
    loading: list.loading,
    options: (list.data?.items ?? []).map((project) => ({
      value: project.id,
      label: project.is_sample ? `${project.name} (SAMPLE)` : project.name,
    })),
  };
}

/** The catalogue's cities as choices. */
export function useCityOptions(): SelectOption[] {
  const list = useLoad("block-cities", () =>
    call(api.GET("/api/v1/admin/cities", { params: { query: { per_page: 100 } } })),
  );
  return (list.data?.items ?? []).map((city) => ({ value: city.id, label: city.name }));
}

/**
 * The library items the page's blocks name, so media fields can show thumbnails: the ones the
 * API returned with the page plus any chosen or uploaded in this session.
 */
export interface BlockMedia {
  get: (id: string | null | undefined) => Media | null;
  remember: (media: Media) => void;
}

export const BlockMediaContext = createContext<BlockMedia>({
  get: () => null,
  remember: () => undefined,
});

export const useBlockMedia = () => useContext(BlockMediaContext);

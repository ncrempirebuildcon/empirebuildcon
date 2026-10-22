"use client";
/**
 * Payment plans: named plans (e.g. construction-linked) made of stages whose percentages must
 * total exactly 100. The running total updates as you type and Save is refused until it is 100.
 *
 * Honest content: there are no "assured return" fields, by design (PaymentPlan schema).
 * INVARIANT: stage percentages total 100 (the API refuses anything else with a 422).
 */
import {
  Button,
  Checkbox,
  NumberField,
  ReorderButtons,
  TextField,
  Textarea,
  moveItem,
} from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { CollectionEditor } from "@/components/admin/CollectionEditor";
import { useCollection } from "@/components/admin/useCollection";
import { orNull, useReportDirty, type ChildTabProps, type PaymentPlan } from "./editorTypes";

interface StageDraft {
  /** Local key so rows keep focus while they move; not sent to the API. */
  key: string;
  label: string;
  percent: number | null;
}

interface PlanDraft {
  name: string;
  description: string;
  is_visible: boolean;
  stages: StageDraft[];
}

let nextKey = 0;
const newKey = () => `stage-${(nextKey += 1)}`;

/**
 * The total in hundredths of a percent, so 33.33 + 33.33 + 33.34 is exactly 100 (floating-point
 * sums like 99.99999999999999 would otherwise block a correct plan).
 */
export function totalHundredths(stages: readonly { percent: number | null }[]): number {
  return stages.reduce((sum, s) => sum + Math.round((s.percent ?? 0) * 100), 0);
}

const toInput = (d: PlanDraft): Schema<"PaymentPlanInput"> => ({
  name: d.name.trim(),
  description: orNull(d.description),
  is_visible: d.is_visible,
  stages: d.stages.map((s, index) => ({
    label: s.label.trim(),
    percent: s.percent ?? 0,
    sort_order: index,
  })),
});

function validate(d: PlanDraft) {
  const errors: Record<string, string> = {};
  if (!d.name.trim()) errors.name = "Name the plan, e.g. Construction-linked plan.";
  if (d.stages.length === 0) errors.stages = "Add at least one stage.";
  d.stages.forEach((s, index) => {
    if (!s.label.trim()) errors[`stages.${index}.label`] = "Name this stage.";
    if (s.percent === null) errors[`stages.${index}.percent`] = "Enter a percentage.";
  });
  if (d.stages.length > 0 && totalHundredths(d.stages) !== 100_00) {
    errors.stages = "The stages must add up to exactly 100%.";
  }
  return errors;
}

export function PaymentPlansTab({ project, canWrite, onChanged, reportDirty }: ChildTabProps) {
  const id = project.id;
  const plans = useCollection<PaymentPlan, PlanDraft>({
    items: project.payment_plans ?? [],
    getId: (p) => p.id,
    getLabel: (p) => p.name,
    emptyDraft: () => ({
      name: "",
      description: "",
      is_visible: true,
      stages: [{ key: newKey(), label: "On booking", percent: null }],
    }),
    toDraft: (p) => ({
      name: p.name,
      description: p.description ?? "",
      is_visible: p.is_visible ?? true,
      stages: p.stages.map((s) => ({ key: newKey(), label: s.label, percent: s.percent })),
    }),
    validate,
    create: (d) =>
      call(
        api.POST("/api/v1/admin/projects/{id}/payment-plans", {
          params: { path: { id } },
          body: toInput(d),
        }),
      ),
    update: (itemId, d) =>
      call(
        api.PATCH("/api/v1/admin/projects/{id}/payment-plans/{item_id}", {
          params: { path: { id, item_id: itemId } },
          body: toInput(d),
        }),
      ),
    remove: (itemId) =>
      call(
        api.DELETE("/api/v1/admin/projects/{id}/payment-plans/{item_id}", {
          params: { path: { id, item_id: itemId } },
        }),
      ),
    reorder: (ids) =>
      call(
        api.PUT("/api/v1/admin/projects/{id}/payment-plans/order", {
          params: { path: { id } },
          body: { ids },
        }),
      ),
    onChanged,
    noun: "payment plan",
  });
  useReportDirty("payment-plans", plans.dirty, reportDirty);

  return (
    <CollectionEditor
      id="payment-plans"
      collection={plans}
      title="Payment plans"
      description="Each plan's stages must add up to exactly 100%."
      addLabel="+ Add payment plan"
      emptyText="No payment plans yet."
      getId={(p) => p.id}
      getLabel={(p) => p.name}
      canWrite={canWrite}
      renderSummary={(p) => (
        <span className="flex flex-col gap-0.5">
          <span>
            <strong className="text-ivory">{p.name}</strong>
            {p.is_visible === false ? <span className="text-muted"> · Hidden</span> : null}
          </span>
          <span className="text-caption text-muted">
            {p.stages.map((s) => `${s.label} ${s.percent}%`).join(" · ")}
          </span>
        </span>
      )}
      renderForm={(d, set, errors) => (
        <div className="grid gap-4">
          <TextField
            label="Plan name"
            required
            maxLength={80}
            value={d.name}
            placeholder="[e.g. Construction-linked plan]"
            onChange={(e) => set({ name: e.target.value })}
            error={errors.name}
          />
          <Textarea
            label="Description (optional)"
            rows={2}
            maxLength={2000}
            value={d.description}
            onChange={(e) => set({ description: e.target.value })}
            error={errors.description}
            hint="Formatting: *bold* · _italic_ · - bullet"
          />
          <StagesEditor stages={d.stages} onChange={(stages) => set({ stages })} errors={errors} />
          <Checkbox
            checked={d.is_visible}
            onChange={(e) => set({ is_visible: e.target.checked })}
            label="Show this plan on the website"
          />
        </div>
      )}
    />
  );
}

function StagesEditor({
  stages,
  onChange,
  errors,
}: {
  stages: StageDraft[];
  onChange: (stages: StageDraft[]) => void;
  errors: Record<string, string>;
}) {
  const total = totalHundredths(stages);
  const difference = Math.abs(100_00 - total) / 100;
  const status =
    total === 100_00
      ? "Total 100% · ready to save"
      : total < 100_00
        ? `Total ${total / 100}% · ${difference}% still to assign`
        : `Total ${total / 100}% · ${difference}% too much`;
  const update = (index: number, patch: Partial<StageDraft>) =>
    onChange(stages.map((s, i) => (i === index ? { ...s, ...patch } : s)));

  return (
    <fieldset className="flex min-w-0 flex-col gap-3 rounded-tile border border-line p-3.5">
      <legend className="px-1 text-small font-semibold text-ivory">Stages</legend>
      <ol className="flex flex-col gap-3">
        {stages.map((stage, index) => (
          <li key={stage.key} className="flex flex-wrap items-start gap-3">
            <TextField
              label={`Stage ${index + 1}`}
              maxLength={120}
              value={stage.label}
              onChange={(e) => update(index, { label: e.target.value })}
              error={errors[`stages.${index}.label`]}
              className="flex-[2_1_220px]"
            />
            <NumberField
              label={`Stage ${index + 1} percent`}
              decimals={2}
              suffix="%"
              value={stage.percent}
              onValueChange={(percent) => update(index, { percent })}
              error={errors[`stages.${index}.percent`]}
              className="flex-[1_1_120px]"
            />
            <span className="flex gap-2 sm:mt-7.5">
              <ReorderButtons
                index={index}
                count={stages.length}
                itemLabel={`stage ${index + 1}`}
                onMove={(from, to) => onChange(moveItem(stages, from, to))}
              />
              <Button
                variant="danger"
                aria-label={`Remove stage ${index + 1}`}
                disabled={stages.length === 1}
                onClick={() => onChange(stages.filter((_, i) => i !== index))}
              >
                Remove
              </Button>
            </span>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button
          variant="secondary"
          onClick={() => onChange([...stages, { key: newKey(), label: "", percent: null }])}
        >
          + Add stage
        </Button>
        <p
          role="status"
          className={`text-small font-bold tabular-nums ${total === 100_00 ? "text-palm" : "text-danger"}`}
        >
          {status}
        </p>
      </div>
      {errors.stages ? <p className="text-caption text-danger">{errors.stages}</p> : null}
    </fieldset>
  );
}

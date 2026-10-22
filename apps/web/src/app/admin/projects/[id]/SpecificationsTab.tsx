"use client";
/**
 * Specifications: what the homes are built and finished with, grouped by category (Structure,
 * Flooring, Kitchen…). Add, edit, remove and reorder; each change saves straight away.
 */
import { TextField, Textarea } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { CollectionEditor } from "@/components/admin/CollectionEditor";
import { useCollection } from "@/components/admin/useCollection";
import { useReportDirty, type ChildTabProps, type Specification } from "./editorTypes";

interface SpecificationDraft {
  category: string;
  text: string;
}

const toInput = (d: SpecificationDraft): Schema<"SpecificationInput"> => ({
  category: d.category.trim(),
  text: d.text.trim(),
});

function validate(d: SpecificationDraft) {
  const errors: Record<string, string> = {};
  if (!d.category.trim()) errors.category = "Enter a category, e.g. Flooring.";
  if (!d.text.trim()) errors.text = "Describe the specification.";
  return errors;
}

export function SpecificationsTab({ project, canWrite, onChanged, reportDirty }: ChildTabProps) {
  const id = project.id;
  const specifications = useCollection<Specification, SpecificationDraft>({
    items: project.specifications ?? [],
    getId: (s) => s.id,
    getLabel: (s) => s.category,
    emptyDraft: () => ({ category: "", text: "" }),
    toDraft: (s) => ({ category: s.category, text: s.text }),
    validate,
    create: (d) =>
      call(
        api.POST("/api/v1/admin/projects/{id}/specifications", {
          params: { path: { id } },
          body: toInput(d),
        }),
      ),
    update: (itemId, d) =>
      call(
        api.PATCH("/api/v1/admin/projects/{id}/specifications/{item_id}", {
          params: { path: { id, item_id: itemId } },
          body: toInput(d),
        }),
      ),
    remove: (itemId) =>
      call(
        api.DELETE("/api/v1/admin/projects/{id}/specifications/{item_id}", {
          params: { path: { id, item_id: itemId } },
        }),
      ),
    reorder: (ids) =>
      call(
        api.PUT("/api/v1/admin/projects/{id}/specifications/order", {
          params: { path: { id } },
          body: { ids },
        }),
      ),
    onChanged,
    noun: "specification",
  });
  useReportDirty("specifications", specifications.dirty, reportDirty);

  return (
    <CollectionEditor
      id="specifications"
      collection={specifications}
      title="Specifications"
      description="Shown on the project page in this order."
      addLabel="+ Add specification"
      emptyText="No specifications yet."
      getId={(s) => s.id}
      getLabel={(s) => s.category}
      canWrite={canWrite}
      renderSummary={(s) => (
        <span className="flex flex-col">
          <strong className="text-ivory">{s.category}</strong>
          <span className="text-small whitespace-pre-line">{s.text}</span>
        </span>
      )}
      renderForm={(d, set, errors) => (
        <div className="grid gap-4">
          <TextField
            label="Category"
            required
            maxLength={60}
            value={d.category}
            placeholder="[e.g. Flooring]"
            onChange={(e) => set({ category: e.target.value })}
            error={errors.category}
          />
          <Textarea
            label="Specification"
            required
            rows={3}
            maxLength={500}
            value={d.text}
            placeholder="[What is used, as written in the agreement for sale]"
            onChange={(e) => set({ text: e.target.value })}
            error={errors.text}
          />
        </div>
      )}
    />
  );
}

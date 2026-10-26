"use client";
/**
 * One group of FAQs (board NoirCmsContent, "FAQs"): the site-wide FAQs (shown on the Contact
 * page) or one project's (shown on its page and in its FAQ structured data). Add, edit, remove,
 * reorder and show/hide, each saved straight away, like a project's child lists
 * (useCollection + CollectionEditor). Used by /admin/faqs and the project editor's FAQs tab.
 *
 * The whole group is loaded (every page of the API's list), and a reorder reads it again and
 * sends all of it, as the API requires (lib/content/faqs.ts; review L10).
 *
 * Permissions (ARCHITECTURE §11): `content.write` adds, edits, removes and reorders;
 * showing or hiding on the website needs `content.publish` (the API's rule, FaqInput). The API
 * checks both again.
 */
import { useState } from "react";
import { Checkbox, Chip, FormattedTextEditor, Switch, TextField } from "@empire/ui";
import { formattedTextToPlain } from "@empire/ui/format";
import { api, call } from "@/lib/api";
import { loadFaqGroup, reorderFaqGroup, type Faq } from "@/lib/content/faqs";
import { problemMessage } from "@/lib/problems";
import { CollectionEditor } from "@/components/admin/CollectionEditor";
import { useCollection } from "@/components/admin/useCollection";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useReportDirty } from "@/components/admin/useUnsavedChanges";
import { useAdminSession } from "@/app/admin/session-context";

interface FaqDraft {
  question: string;
  answer: string;
  is_visible: boolean;
}

function validate(draft: FaqDraft) {
  const errors: Record<string, string> = {};
  if (!draft.question.trim()) errors.question = "Enter the question.";
  if (!draft.answer.trim()) errors.answer = "Enter the answer.";
  return errors;
}

export interface FaqManagerProps {
  /** The project whose FAQs these are, or null for the site-wide FAQs. */
  projectId: string | null;
  /** Heading of the card, e.g. "Site-wide FAQs" or "FAQs". */
  title: string;
  description: string;
  /** Tells the screen whether a FAQ form has unsaved changes (for the leave warning). */
  onDirtyChange?: (dirty: boolean) => void;
}

export function FaqManager({ projectId, title, description, onDirtyChange }: FaqManagerProps) {
  // WHY the whole group: a reorder must name every FAQ of it (lib/content/faqs.ts).
  const list = useLoad(`faqs:${projectId ?? "site"}`, () => loadFaqGroup(projectId));
  if (list.error && !list.data) {
    return (
      <ErrorPanel
        message={problemMessage(list.error, "Couldn't load the FAQs.")}
        onRetry={list.reload}
      />
    );
  }
  if (!list.data) return <LoadingPanel label="Loading FAQs…" rows={4} />;
  return (
    <FaqList
      items={list.data}
      projectId={projectId}
      title={title}
      description={description}
      refresh={list.refresh}
      onDirtyChange={onDirtyChange}
    />
  );
}

function FaqList({
  items,
  projectId,
  title,
  description,
  refresh,
  onDirtyChange,
}: {
  items: Faq[];
  projectId: string | null;
  title: string;
  description: string;
  refresh: () => Promise<unknown>;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { can } = useAdminSession();
  const canWrite = can("content.write");
  const canShow = can("content.publish");
  const [toggling, setToggling] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const sorted = [...items].sort((a, b) => a.sort_order - b.sort_order);

  const faqs = useCollection<Faq, FaqDraft>({
    items: sorted,
    getId: (faq) => faq.id,
    getLabel: (faq) => faq.question,
    emptyDraft: () => ({ question: "", answer: "", is_visible: canShow }),
    toDraft: (faq) => ({ question: faq.question, answer: faq.answer, is_visible: faq.is_visible }),
    validate,
    create: (draft) =>
      call(
        api.POST("/api/v1/admin/faqs", {
          body: {
            project_id: projectId,
            question: draft.question.trim(),
            answer: draft.answer,
            sort_order: null,
            is_visible: draft.is_visible,
            translations: {},
          },
        }),
      ),
    update: (id, draft) => {
      const before = items.find((faq) => faq.id === id);
      return call(
        api.PATCH("/api/v1/admin/faqs/{id}", {
          params: { path: { id } },
          body: {
            question: draft.question.trim(),
            answer: draft.answer,
            // WHY only when changed: showing or hiding needs content.publish; an editor without
            // it can still fix a typo.
            ...(before && before.is_visible !== draft.is_visible
              ? { is_visible: draft.is_visible }
              : {}),
          },
        }),
      );
    },
    remove: (id) => call(api.DELETE("/api/v1/admin/faqs/{id}", { params: { path: { id } } })),
    reorder: (ids) => reorderFaqGroup(projectId, ids),
    onChanged: refresh,
    noun: "FAQ",
  });
  useReportDirty(onDirtyChange, faqs.dirty);

  async function toggle(faq: Faq, visible: boolean) {
    setToggling(faq.id);
    setToggleError(null);
    try {
      await call(
        api.PATCH("/api/v1/admin/faqs/{id}", {
          params: { path: { id: faq.id } },
          body: { is_visible: visible },
        }),
      );
      await refresh();
    } catch (err) {
      setToggleError(problemMessage(err, "Couldn't change whether the FAQ is shown."));
    } finally {
      setToggling(null);
    }
  }

  const idPrefix = `faqs-${projectId ?? "site"}`;
  return (
    <>
      {toggleError ? (
        <p className="text-small text-danger" role="alert">
          {toggleError}
        </p>
      ) : null}
      <CollectionEditor
        id={idPrefix}
        collection={faqs}
        title={title}
        description={description}
        addLabel="+ Add FAQ"
        emptyText="No FAQs here yet."
        getId={(faq) => faq.id}
        getLabel={(faq) => faq.question}
        canWrite={canWrite}
        renderSummary={(faq) => (
          <span className="flex flex-col gap-1.5">
            <span className="flex flex-wrap items-center gap-2">
              <strong className="text-ivory">{faq.question}</strong>
              {faq.is_sample ? <Chip variant="sample">SAMPLE</Chip> : null}
              <Chip variant={faq.is_visible ? "published" : "draft"}>
                {faq.is_visible ? "Shown" : "Hidden"}
              </Chip>
            </span>
            <span className="line-clamp-2 text-caption text-muted">
              {formattedTextToPlain(faq.answer)}
            </span>
            {canShow ? (
              <Switch
                checked={faq.is_visible}
                busy={toggling === faq.id}
                onChange={(visible) => void toggle(faq, visible)}
                label="Show on website"
                stateText={{ on: "Shown", off: "Hidden" }}
                context={faq.question}
              />
            ) : null}
          </span>
        )}
        renderForm={(draft, set, errors) => (
          <div className="grid gap-4">
            <TextField
              label="Question"
              required
              maxLength={200}
              value={draft.question}
              onChange={(event) => set({ question: event.target.value })}
              error={errors.question}
            />
            <FormattedTextEditor
              label="Answer"
              required
              rows={5}
              limit={4000}
              value={draft.answer}
              onChange={(answer) => set({ answer })}
              error={errors.answer}
            />
            <Checkbox
              checked={draft.is_visible}
              disabled={!canShow}
              onChange={(event) => set({ is_visible: event.target.checked })}
              label="Show on the website"
              hint={
                canShow ? undefined : "Showing or hiding FAQs needs the content.publish permission."
              }
            />
          </div>
        )}
      />
    </>
  );
}

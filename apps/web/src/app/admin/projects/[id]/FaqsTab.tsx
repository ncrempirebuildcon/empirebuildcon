"use client";
/**
 * The project's FAQs (spec Phase 4 part 4 §4): the same list, order and show/hide controls as
 * /admin/faqs, scoped to this project. Shown on the project page and in its FAQ structured data
 * (Phase 5). Writing needs `content.write`, showing needs `content.publish` (FaqManager.tsx).
 */
import { useCallback } from "react";
import Link from "next/link";
import { FAQS_PATH } from "@/lib/routes";
import { FaqManager } from "@/components/admin/content/FaqManager";
import type { ProjectAdmin } from "./projectForm";

export function FaqsTab({
  project,
  reportDirty,
}: {
  project: ProjectAdmin;
  reportDirty: (key: string, dirty: boolean) => void;
}) {
  // WHY useCallback: FaqManager reports through an effect keyed on this function.
  const onDirtyChange = useCallback((dirty: boolean) => reportDirty("faqs", dirty), [reportDirty]);
  return (
    <div className="flex flex-col gap-3">
      <FaqManager
        projectId={project.id}
        title="FAQs"
        description="Shown on this project's page, in this order, and in its FAQ structured data."
        onDirtyChange={onDirtyChange}
      />
      <p className="text-caption text-muted">
        Site-wide FAQs (the Contact page) are under{" "}
        <Link href={FAQS_PATH} className="underline">
          Offers &amp; blog → FAQs
        </Link>
        .
      </p>
    </div>
  );
}

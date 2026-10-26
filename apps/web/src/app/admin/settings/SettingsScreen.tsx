"use client";
/**
 * Settings (board NoirCmsSettings): a vertical list of sections on the left and the chosen
 * section on the right, each with its own Save, the permission it needs ("Needs …"), and
 * read-only fields for roles that can't change it. The open section is in the address
 * (`?tab=company|rera|…|consent|flags`; the dashboard's consent tasks link to `?tab=consent`).
 *
 * How it works:
 *   1. `GET /admin/settings` is loaded once; every section reads its groups from that answer and
 *      saves its own groups with `PATCH /admin/settings/{group}`.
 *   2. Every section is drawn once and kept (the others hidden, not removed), so switching
 *      sections never loses typing. One unsaved-changes guard covers them all.
 *   3. After a save the answer replaces that group in memory; other sections keep their drafts.
 *
 * SECURITY: what a role can change is decided by the API on every save (ARCHITECTURE §11);
 * `canSaveSection` only decides what is offered. No secret is ever part of settings: email
 * and other keys live in the server environment and are shown as "set" or "not set" only.
 */
import { useCallback, useMemo, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { TabPanel, Tabs } from "@empire/ui";
import { problemMessage } from "@/lib/problems";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { useAdminSession } from "../session-context";
import {
  SETTINGS_SECTIONS,
  canSaveSection,
  isSettingsSection,
  sectionNeeds,
  type SettingsSectionId,
} from "./sections";
import { SectionBody } from "./SectionBody";
import { useSettings } from "./useSettings";

export function SettingsScreen() {
  const params = useSearchParams();
  const { can } = useAdminSession();
  // WHY from the address and not state: links to `?tab=…` (the dashboard, Privacy → Consent
  // texts) and history.replaceState below both update useSearchParams, so the open section
  // always matches the address.
  const fromUrl = params.get("tab");
  const tab: SettingsSectionId = isSettingsSection(fromUrl) ? fromUrl : "company";
  const parts = useDirtyParts();
  const { report } = parts;
  const { dialog } = useUnsavedChanges(parts.dirty);
  // WHY stable functions: useReportDirty re-runs when its callback changes; a new arrow on every
  // render would report "clean" and "dirty" in turn forever.
  const reporters = useMemo(
    () =>
      Object.fromEntries(
        SETTINGS_SECTIONS.map((section) => [
          section.id,
          (dirty: boolean) => report(section.id, dirty),
        ]),
      ) as Record<SettingsSectionId, (dirty: boolean) => void>,
    [report],
  );
  const settings = useSettings();

  const setTab = useCallback((next: string) => {
    if (!isSettingsSection(next)) return;
    // WHY: keep the section in the address so a reload or a shared link opens the same one.
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url);
  }, []);

  return (
    <>
      <p className="text-small text-muted">
        Company details, contacts, lead routing, tracking, integrations, SEO, privacy and feature
        flags. Every save is written to the audit log.
      </p>
      <div className="flex flex-wrap items-start gap-6">
        <Tabs
          label="Settings sections"
          idPrefix="settings"
          orientation="vertical"
          selected={tab}
          onSelect={setTab}
          className="w-full md:w-56 md:shrink-0"
          tabs={SETTINGS_SECTIONS.map((section) => ({
            id: section.id,
            label: (
              <span className="flex flex-col gap-px">
                {section.label}
                {/* WHY hidden on phones: ten sections with hints fill a whole phone screen. */}
                <span className="hidden text-xs font-medium text-muted md:block">
                  {section.hint}
                </span>
              </span>
            ),
          }))}
        />
        <div className="min-w-0 flex-[1_1_480px]">
          {settings.error ? (
            <ErrorPanel
              message={problemMessage(settings.error, "Couldn't load the settings.")}
              onRetry={settings.reload}
            />
          ) : !settings.data ? (
            <LoadingPanel label="Loading settings…" rows={8} />
          ) : (
            SETTINGS_SECTIONS.map((section) => (
              <TabPanel
                key={section.id}
                idPrefix="settings"
                tabId={section.id}
                selected={tab === section.id}
              >
                <SectionFrame
                  id={section.id}
                  title={section.label}
                  intro={section.intro}
                  permission={sectionNeeds(section.id, settings)}
                >
                  <SectionBody
                    id={section.id}
                    settings={settings}
                    canSave={canSaveSection(section.id, settings, can)}
                    onDirtyChange={reporters[section.id]}
                  />
                </SectionFrame>
              </TabPanel>
            ))
          )}
        </div>
      </div>
      {dialog}
    </>
  );
}

function SectionFrame({
  id,
  title,
  intro,
  permission,
  children,
}: {
  id: string;
  title: string;
  intro: string;
  permission: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={`settings-${id}-title`}
      className="flex flex-col gap-4.5 rounded-card border border-line bg-noir-800 px-4 py-5 md:px-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line pb-3.5">
        <div className="min-w-0 flex-[1_1_260px]">
          <h2 id={`settings-${id}-title`} className="text-xl font-bold">
            {title}
          </h2>
          <p className="mt-0.5 text-small text-muted">{intro}</p>
        </div>
        <span className="rounded-pill border border-gold-500/60 px-2.5 py-0.5 text-xs font-bold whitespace-nowrap text-gold-300">
          Needs <code>{permission}</code>
        </span>
      </div>
      {children}
    </section>
  );
}

"use client";
/**
 * Settings → RERA (board NoirCmsSettings): the "show RERA details everywhere" rule, shown on and
 * locked, the registering authority (UP-RERA and its portal, fixed), and the optional promoter
 * registration number.
 *
 * COMPLIANCE (AGENTS.md "Honest content", D-002): the UP-RERA number, QR code and up-rera.in
 * show on every project, property and ad view. The switch is drawn so staff can see the rule,
 * but it can't be turned off here or in the API. Changing this needs owner approval.
 */
import Link from "next/link";
import { Chip, Switch } from "@empire/ui";
import { PAGES_PATH } from "@/lib/routes";
import { RERA_FIELDS } from "./fields";
import { GroupForm } from "./GroupForm";
import { readOnlyReason, type SectionProps } from "./sections";

export function ReraSection({ settings, canSave, onDirtyChange }: SectionProps) {
  const regulator = settings.data?.regulator;
  const authority = regulator?.authority ?? "UP-RERA";
  // SECURITY: the portal link is fixed by the API (a literal); never follow anything else.
  const portal =
    regulator?.website?.startsWith("https://") === true
      ? regulator.website
      : "https://www.up-rera.in";
  return (
    <div className="flex flex-col gap-4.5">
      <div className="flex flex-wrap items-center gap-4 rounded-card border border-gold-line-strong bg-noir-700 px-4.5 py-4">
        <div className="min-w-0 flex-[1_1_280px]">
          <p className="font-bold text-ivory">
            Show RERA number, QR code and up-rera.in link on every project page and card
          </p>
          <p id="rera-rule" className="mt-0.5 text-caption text-muted">
            Always on. UP-RERA&apos;s advertising directions need them, so this can&apos;t be
            switched off. A project can&apos;t be published until its RERA number and QR code are
            added.
          </p>
        </div>
        <Switch
          checked
          disabled
          onChange={() => undefined}
          label="Show RERA details"
          stateText={{ on: "On · locked", off: "Off" }}
          aria-describedby="rera-rule"
        />
      </div>

      <div
        role="region"
        aria-label="Registering authority"
        tabIndex={0}
        className="relative overflow-x-auto rounded-card border border-line bg-noir-900"
      >
        <table className="w-full min-w-[620px] border-collapse text-table">
          <caption className="sr-only">Where Empire&apos;s projects are registered</caption>
          <thead>
            <tr className="text-left text-xs tracking-[0.08em] text-gold-400 uppercase">
              <th scope="col" className="px-4 py-3">
                State
              </th>
              <th scope="col" className="px-2.5 py-3">
                Authority
              </th>
              <th scope="col" className="px-2.5 py-3">
                Portal
              </th>
              <th scope="col" className="px-4 py-3">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-line">
              <th scope="row" className="px-4 py-3 text-left font-bold text-ivory">
                {regulator?.state_name ?? "Uttar Pradesh"}
              </th>
              <td className="px-2.5 py-3">
                {regulator?.authority_name ?? "Uttar Pradesh Real Estate Regulatory Authority"} (
                {authority})
              </td>
              <td className="px-2.5 py-3">
                <a href={portal} target="_blank" rel="noreferrer noopener">
                  up-rera.in<span className="sr-only"> (opens in a new tab)</span>
                </a>
              </td>
              <td className="px-4 py-3">
                <Chip variant="published">Active</Chip>
              </td>
            </tr>
          </tbody>
        </table>
        <p className="border-t border-line px-4 py-3 text-caption text-muted">
          The authority and portal are fixed. Another state&apos;s authority can be added when
          Empire launches a project there.
        </p>
      </div>

      <GroupForm
        label="RERA settings"
        fields={RERA_FIELDS}
        values={settings.groups}
        readOnly={!canSave}
        readOnlyReason={readOnlyReason("rera", settings)}
        onSave={settings.save}
        onDirtyChange={onDirtyChange}
        after={
          <p className="text-small">
            The RERA disclaimer shown under every project lives with the legal pages:{" "}
            <Link href={`${PAGES_PATH}?kind=legal`} className="font-bold underline">
              Legal pages
            </Link>
            .
          </p>
        }
      />
    </div>
  );
}

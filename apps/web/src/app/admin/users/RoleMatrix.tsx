"use client";
/**
 * "What each role can do" (board NoirCmsUsers): the permission matrix from GET /admin/roles,
 * grouped as on the board, with a role picker in the column headers that highlights a column and
 * says what the role is for.
 *
 * The rows, their groups and plain-English lines come from GET /admin/permissions, the role
 * columns, summaries and counts of active accounts from GET /admin/roles.
 *
 * SECURITY: the ticks come only from the API's matrix (apps/api users/roles.py, ARCHITECTURE
 * §11), which is also what the API enforces on every call. Nothing here grants anything.
 *
 * Accessibility: each tick or dash has words for screen readers ("Allowed for Sales"); the
 * picker buttons use `aria-pressed`, and the summary line is a polite status, so the highlight
 * colour is never the only signal (WCAG 1.4.1).
 */
import { useMemo, useState } from "react";
import { cx } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import {
  ROLE_ORDER,
  ROLE_SUMMARIES,
  groupPermissions,
  userCountText,
  type RoleKey,
} from "@/lib/users";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";

type Role = Schema<"Role">;
type PermissionRow = Schema<"Permission">;

export function RoleMatrix() {
  const load = useLoad("roles", () =>
    Promise.all([call(api.GET("/api/v1/admin/roles")), call(api.GET("/api/v1/admin/permissions"))]),
  );
  const [selected, setSelected] = useState<RoleKey>("sales");
  const roles = useMemo(() => {
    const byKey = new Map((load.data?.[0] ?? []).map((role) => [role.key, role]));
    return ROLE_ORDER.map((key) => byKey.get(key)).filter((role): role is Role => !!role);
  }, [load.data]);
  const groups = groupPermissions(load.data?.[1] ?? []);
  const current = roles.find((role) => role.key === selected);

  return (
    <section
      aria-labelledby="roles-title"
      className="flex flex-col overflow-hidden rounded-card border border-line bg-noir-800"
    >
      <div className="flex flex-col gap-2 border-b border-line px-4.5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <h2 id="roles-title" className="text-base font-bold">
            What each role can do
          </h2>
          <span className="text-caption text-muted">
            Select a role to highlight it · the API checks every one of these on every call
          </span>
        </div>
        {current ? (
          <p
            role="status"
            className="flex flex-wrap items-baseline gap-2.5 rounded-tile border-l-3 border-gold-500 bg-noir-700 px-3.5 py-2.5 text-small"
          >
            <strong className="text-gold-300">{current.name}</strong>
            <span>{current.summary || ROLE_SUMMARIES[current.key]}</span>
          </p>
        ) : null}
      </div>
      {load.error ? (
        <ErrorPanel
          message={problemMessage(load.error, "Couldn't load the roles.")}
          onRetry={load.reload}
        />
      ) : !load.data ? (
        <LoadingPanel label="Loading the roles…" rows={6} />
      ) : (
        <div
          role="region"
          aria-label="Role permissions table"
          tabIndex={0}
          className="relative overflow-x-auto"
        >
          <table className="w-full min-w-[900px] border-collapse text-table">
            <caption className="sr-only">Permissions of each role</caption>
            <thead>
              <tr className="text-left">
                <th
                  scope="col"
                  className="px-4.5 py-2.5 align-bottom text-xs tracking-[0.08em] text-gold-400 uppercase"
                >
                  Permission
                </th>
                {roles.map((role) => {
                  const on = role.key === selected;
                  return (
                    <th
                      key={role.key}
                      scope="col"
                      className={cx("w-32 px-1.5 py-1.5 text-center", on && "bg-gold-tint")}
                    >
                      <button
                        type="button"
                        aria-pressed={on}
                        onClick={() => setSelected(role.key)}
                        className={cx(
                          "flex min-h-11 w-full flex-col items-center gap-0.5 rounded-tile border px-1.5 py-2 text-caption font-extrabold",
                          on ? "border-gold-500 text-gold-300" : "border-line-strong text-ivory",
                        )}
                      >
                        {ROLE_LABELS[role.key] ?? role.name}
                        <span className="text-xs font-semibold text-muted">
                          {userCountText(role.user_count)}
                        </span>
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <GroupRows
                  key={group.name}
                  name={group.name}
                  rows={group.rows}
                  roles={roles}
                  selected={selected}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="border-t border-line px-4.5 py-3 text-caption text-muted">
        The CMS hides buttons a role can&apos;t use, but the server is the real gate. Sales users
        without &ldquo;see every lead&rdquo; only ever see their own leads, in lists, exports and
        reports.
      </p>
    </section>
  );
}

function GroupRows({
  name,
  rows,
  roles,
  selected,
}: {
  name: string;
  rows: PermissionRow[];
  roles: Role[];
  selected: RoleKey;
}) {
  return (
    <>
      <tr className="border-t border-line">
        <th
          scope="colgroup"
          colSpan={roles.length + 1}
          className="px-4.5 pt-3 pb-1.5 text-left font-display text-xs font-semibold tracking-[0.2em] text-gold-400 uppercase"
        >
          {name}
        </th>
      </tr>
      {rows.map((row) => (
        <tr key={row.key} className="border-t border-line">
          <th scope="row" className="px-4.5 py-2 text-left font-medium">
            <span className="flex flex-col">
              <code className="text-caption font-bold text-ivory">{row.key}</code>
              <span className="text-caption text-muted">{row.allows}</span>
            </span>
          </th>
          {roles.map((role) => {
            const yes = row.roles.includes(role.key);
            const label = ROLE_LABELS[role.key] ?? role.name;
            return (
              <td
                key={role.key}
                className={cx("px-1.5 py-2 text-center", role.key === selected && "bg-gold-tint")}
              >
                {yes ? (
                  <span className="text-base font-extrabold text-gold-400">
                    <span aria-hidden="true">✓</span>
                    <span className="sr-only">Allowed for {label}</span>
                  </span>
                ) : (
                  <span className="font-bold text-muted">
                    <span aria-hidden="true">—</span>
                    <span className="sr-only">Not allowed for {label}</span>
                  </span>
                )}
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}

"use client";
/**
 * Users & roles (board NoirCmsUsers, super-admin only): "+ Invite user", the staff table with
 * status, two-factor and last sign-in, a panel beside the table to manage one account (role,
 * unlock, reset or setup link, sign out everywhere, reset two-factor, deactivate), and the role
 * matrix. Search, filters, the page and the open account live in the address
 * (`?q=&role=&status=&page=&user=<id>`).
 *
 * SECURITY: the API is the gate for every action (`users.manage`); it also refuses demoting or
 * deactivating the last usable super-admin (rows locked against races, SECURITY.md §2) and never
 * returns a setup or reset link. This screen only asks first and shows the answer.
 */
import Link from "next/link";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, Button, Chip, Select, TextField, type ChipVariant } from "@empire/ui";
import { api, call } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { ROLE_LABELS } from "@/lib/labels";
import { problemMessage } from "@/lib/problems";
import { AUDIT_PATH, USERS_PATH } from "@/lib/routes";
import {
  ACCOUNT_STATUS,
  ROLE_ORDER,
  accountStatus,
  initials,
  type AccountStatus,
  type RoleKey,
} from "@/lib/users";
import { Pager, pageFrom } from "@/components/admin/Pager";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useDirtyParts, useUnsavedChanges } from "@/components/admin/useUnsavedChanges";
import { useAdminSession } from "../session-context";
import { InviteForm } from "./InviteForm";
import { RoleMatrix } from "./RoleMatrix";
import { UserPanel } from "./UserPanel";
import { statusNote, twoFactorText, type StaffUser } from "./userText";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PER_PAGE = 25;

export const STATUS_CHIP: Record<AccountStatus, ChipVariant> = {
  active: "published",
  invited: "scheduled",
  locked: "soldOut",
  deactivated: "archived",
};

interface Filters {
  q: string;
  role: RoleKey | "";
  status: AccountStatus | "";
  page: number;
  user: string | null;
}

function hrefFor(filters: Filters): string {
  const search = new URLSearchParams();
  if (filters.q) search.set("q", filters.q);
  if (filters.role) search.set("role", filters.role);
  if (filters.status) search.set("status", filters.status);
  if (filters.page > 1) search.set("page", String(filters.page));
  if (filters.user) search.set("user", filters.user);
  const query = search.toString();
  return query ? `${USERS_PATH}?${query}` : USERS_PATH;
}

export function UsersScreen() {
  const params = useSearchParams();
  const { me } = useAdminSession();
  const rawUser = params.get("user") ?? "";
  const filters: Filters = {
    q: (params.get("q") ?? "").slice(0, 80),
    role: ROLE_ORDER.find((role) => role === params.get("role")) ?? "",
    status:
      (Object.keys(ACCOUNT_STATUS) as AccountStatus[]).find((s) => s === params.get("status")) ??
      "",
    page: pageFrom(params.get("page")),
    user: UUID_RE.test(rawUser) ? rawUser : null,
  };
  const [inviteOpen, setInviteOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const parts = useDirtyParts();
  const { report } = parts;
  const onInviteDirty = useCallback((dirty: boolean) => report("invite", dirty), [report]);
  const onPanelDirty = useCallback((dirty: boolean) => report("panel", dirty), [report]);
  const { dialog, leave } = useUnsavedChanges(parts.dirty);

  const listKey = `users:${filters.q}:${filters.role}:${filters.status}:${filters.page}`;
  const list = useLoad(listKey, () =>
    call(
      api.GET("/api/v1/admin/users", {
        params: {
          query: {
            q: filters.q || undefined,
            page: filters.page,
            per_page: PER_PAGE,
            role: filters.role || undefined,
            status: filters.status || undefined,
          },
        },
      }),
    ),
  );
  const users = useMemo<StaffUser[]>(() => list.data?.items ?? [], [list.data]);
  const current = filters.user ? users.find((u) => u.id === filters.user) : undefined;
  const go = (patch: Partial<Filters>) =>
    leave(hrefFor({ ...filters, ...patch }), { replace: true });

  async function unlock(user: StaffUser) {
    try {
      await call(
        api.POST("/api/v1/admin/users/{id}/unlock", { params: { path: { id: user.id } } }),
      );
      setToast(
        `${user.name} is unlocked and can sign in again. This is recorded in the audit log.`,
      );
      await list.refresh();
    } catch (err) {
      setToast(null);
      setActionError(problemMessage(err, `Couldn't unlock ${user.name}.`));
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3.5">
        <p className="min-w-0 flex-[1_1_320px] text-small text-muted">
          Who can sign in to the CMS, and what each role can do. Only the super-admin can change
          these.
        </p>
        <Button
          aria-expanded={inviteOpen}
          aria-controls="invite-user"
          onClick={() => setInviteOpen((open) => !open)}
        >
          {inviteOpen ? "Close" : "+ Invite user"}
        </Button>
      </div>
      {inviteOpen ? (
        <div id="invite-user">
          <InviteForm
            onDirtyChange={onInviteDirty}
            onInvited={(user) => {
              setInviteOpen(false);
              setActionError(null);
              setToast(
                `Invite sent to ${user.email}. The link works once and expires; they choose their own password.`,
              );
              void list.refresh().catch(() => undefined);
            }}
          />
        </div>
      ) : null}
      {toast ? <Alert tone="success">{toast}</Alert> : null}
      {actionError ? <Alert tone="error">{actionError}</Alert> : null}

      <UserFilters
        key={filters.q}
        filters={filters}
        onApply={(patch) => go({ ...patch, page: 1, user: null })}
      />

      <div className="flex flex-wrap items-start gap-5">
        <section
          aria-labelledby="users-title"
          className="flex min-w-0 flex-[2_1_560px] flex-col overflow-hidden rounded-card border border-line bg-noir-800"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4.5 py-3.5">
            <h2 id="users-title" className="text-base font-bold">
              Users{" "}
              {list.data ? (
                <span className="font-semibold text-muted">· {list.data.meta.total}</span>
              ) : null}
            </h2>
            <span className="text-caption text-muted">
              Sessions end after 8 hours idle or 7 days
            </span>
          </div>
          {list.error ? (
            <ErrorPanel
              message={problemMessage(list.error, "Couldn't load users.")}
              onRetry={list.reload}
            />
          ) : !list.data ? (
            <LoadingPanel label="Loading users…" rows={5} />
          ) : (
            <>
              <UsersTable
                users={users}
                selected={filters.user}
                meId={me.id}
                busy={list.loading}
                onOpen={(user) => go({ user: user.id })}
                onUnlock={(user) => void unlock(user)}
                empty={
                  <EmptyState
                    title={
                      filters.q || filters.role || filters.status
                        ? "No users match these filters."
                        : "No staff accounts yet."
                    }
                  />
                }
              />
              <div className="border-t border-line px-4 py-2">
                <Pager
                  page={list.data.meta.page}
                  perPage={list.data.meta.per_page}
                  total={list.data.meta.total}
                  pages={list.data.meta.pages}
                  hrefFor={(page) => hrefFor({ ...filters, page, user: null })}
                  noun="users"
                  singular="user"
                />
              </div>
            </>
          )}
          <p className="border-t border-line px-4.5 py-3 text-caption text-muted">
            An account locks for 15 minutes after 5 failed sign-ins; the super-admin can unlock it
            sooner. Every change is written to the{" "}
            <Link href={AUDIT_PATH} className="underline">
              audit log
            </Link>
            .
          </p>
        </section>
        {current ? (
          <UserPanel
            key={current.id}
            user={current}
            isMe={current.id === me.id}
            onDirtyChange={onPanelDirty}
            onDone={async (message) => {
              setActionError(null);
              setToast(message);
              await list.refresh().catch(() => undefined);
            }}
            onClose={() => go({ user: null })}
          />
        ) : filters.user && list.data ? (
          <Alert tone="info" title="This account isn't in the list.">
            It may be on another page of the list or outside the filters.
          </Alert>
        ) : null}
      </div>

      <RoleMatrix />
      {dialog}
    </>
  );
}

function UsersTable({
  users,
  selected,
  meId,
  busy,
  onOpen,
  onUnlock,
  empty,
}: {
  users: StaffUser[];
  selected: string | null;
  meId: string;
  busy: boolean;
  onOpen: (user: StaffUser) => void;
  onUnlock: (user: StaffUser) => void;
  empty: ReactNode;
}) {
  if (users.length === 0) return <>{empty}</>;
  return (
    <div
      role="region"
      aria-label="Users table"
      tabIndex={0}
      className="relative overflow-x-auto"
      aria-busy={busy || undefined}
    >
      <table className="w-full min-w-[820px] border-collapse text-table">
        <caption className="sr-only">Staff accounts</caption>
        <thead>
          <tr className="text-left text-xs tracking-[0.08em] text-gold-400 uppercase">
            <th scope="col" className="px-4.5 py-3">
              User
            </th>
            <th scope="col" className="px-2.5 py-3">
              Role
            </th>
            <th scope="col" className="px-2.5 py-3">
              Status
            </th>
            <th scope="col" className="px-2.5 py-3">
              Two-factor
            </th>
            <th scope="col" className="px-2.5 py-3">
              Last sign-in
            </th>
            <th scope="col" className="px-4.5 py-3 text-right">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => {
            const status = accountStatus(user);
            const note = statusNote(user, status);
            return (
              <tr
                key={user.id}
                className={`border-t border-line align-top ${user.id === selected ? "bg-gold-tint" : ""}`}
              >
                <th scope="row" className="px-4.5 py-3 text-left font-normal">
                  <span className="flex items-center gap-3">
                    <span
                      aria-hidden="true"
                      className="flex size-8.5 shrink-0 items-center justify-center rounded-pill border border-line-strong bg-noir-700 text-xs font-extrabold text-gold-300"
                    >
                      {initials(user.name)}
                    </span>
                    <span className="flex min-w-0 flex-col">
                      <span className="flex flex-wrap items-center gap-2">
                        <strong className="text-ivory">{user.name}</strong>
                        {user.id === meId ? (
                          <span className="text-xs text-muted">(you)</span>
                        ) : null}
                        {/* WHY by name: `seed --sample` (development only) names its accounts
                            "Sample …"; the API has no sample flag on accounts. */}
                        {/^Sample\b/.test(user.name) ? <Chip variant="sample">Sample</Chip> : null}
                      </span>
                      <span className="text-caption [overflow-wrap:anywhere] text-muted">
                        {user.email}
                      </span>
                    </span>
                  </span>
                </th>
                <td className="px-2.5 py-3">{ROLE_LABELS[user.role] ?? user.role}</td>
                <td className="px-2.5 py-3">
                  <Chip variant={STATUS_CHIP[status]}>{ACCOUNT_STATUS[status]}</Chip>
                  {note ? <span className="mt-1 block text-xs text-muted">{note}</span> : null}
                </td>
                <td className="px-2.5 py-3 text-caption">{twoFactorText(user)}</td>
                <td className="px-2.5 py-3 text-caption whitespace-nowrap">
                  {user.last_login_at ? formatDateTime(user.last_login_at) : "Never"}
                </td>
                <td className="px-4.5 py-3 text-right whitespace-nowrap">
                  <span className="inline-flex flex-wrap justify-end gap-2">
                    {status === "locked" ? (
                      <Button variant="secondary" onClick={() => onUnlock(user)}>
                        Unlock<span className="sr-only"> {user.name}</span>
                      </Button>
                    ) : null}
                    <Button
                      variant="secondary"
                      aria-pressed={user.id === selected}
                      onClick={() => onOpen(user)}
                    >
                      Manage<span className="sr-only"> {user.name}</span>
                    </Button>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function UserFilters({
  filters,
  onApply,
}: {
  filters: Filters;
  onApply: (patch: Partial<Filters>) => void;
}) {
  const [query, setQuery] = useState(filters.q);
  return (
    <form
      role="search"
      aria-label="Filter users"
      onSubmit={(event) => {
        event.preventDefault();
        onApply({ q: query.trim() });
      }}
      className="flex flex-wrap items-end gap-3"
    >
      <div className="flex min-w-60 flex-[2_1_260px] items-end gap-2">
        <TextField
          label="Search"
          type="search"
          placeholder="Name or email"
          value={query}
          maxLength={80}
          onChange={(event) => setQuery(event.target.value)}
          className="flex-1"
        />
        <Button type="submit" variant="secondary" className="mb-0.75">
          Search
        </Button>
      </div>
      <Select
        label="Role"
        value={filters.role}
        placeholder="Any role"
        options={ROLE_ORDER.map((role) => ({ value: role, label: ROLE_LABELS[role] ?? role }))}
        onChange={(event) =>
          onApply({ role: ROLE_ORDER.find((role) => role === event.target.value) ?? "" })
        }
        className="flex-[1_1_170px]"
      />
      <Select
        label="Status"
        value={filters.status}
        placeholder="Any status"
        options={(Object.keys(ACCOUNT_STATUS) as AccountStatus[]).map((status) => ({
          value: status,
          label: ACCOUNT_STATUS[status],
        }))}
        onChange={(event) =>
          onApply({
            status:
              (Object.keys(ACCOUNT_STATUS) as AccountStatus[]).find(
                (status) => status === event.target.value,
              ) ?? "",
          })
        }
        className="flex-[1_1_170px]"
      />
    </form>
  );
}

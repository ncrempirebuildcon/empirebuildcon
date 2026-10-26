"use client";
/**
 * Settings → Feature flags (board NoirCmsSettings, CODE_STYLE §6): each flag with a plain title,
 * its key, the API's description, and a switch that saves at once (`PATCH /admin/flags/{key}`,
 * audited). Flags for features not built yet show "Off · not built yet" and can't be switched.
 *
 * SECURITY (SECURITY.md §1, D-027): only the super-admin can switch `admin_2fa`, and turning it
 * on is refused unless that super-admin has two-factor on themselves, so nobody can lock every
 * admin out. The API says per flag, for this viewer, whether it can be switched and why not
 * (`can_switch`, `cannot_switch_reason`); the switch shows that before anyone tries, and the
 * API enforces it on the PATCH.
 */
import Link from "next/link";
import { useState } from "react";
import { Alert, Switch } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { formatDateTime } from "@/lib/dates";
import { problemMessage } from "@/lib/problems";
import { ACCOUNT_PATH } from "@/lib/routes";
import { ErrorPanel, LoadingPanel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../session-context";

type Flag = Schema<"FeatureFlag">;

export function FlagsSection() {
  const { me } = useAdminSession();
  const load = useLoad("settings:flags", () => call(api.GET("/api/v1/admin/flags")));
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  async function flip(flag: Flag, enabled: boolean) {
    setBusyKey(flag.key);
    setMessage(null);
    try {
      const saved = await call(
        api.PATCH("/api/v1/admin/flags/{key}", {
          params: { path: { key: flag.key } },
          body: { enabled },
        }),
      );
      load.replace((load.data ?? []).map((f) => (f.key === saved.key ? saved : f)));
      setMessage({
        tone: "success",
        text: `${saved.title} is ${saved.enabled ? "on" : "off"}. This is recorded in the audit log.`,
      });
    } catch (err) {
      setMessage({ tone: "error", text: problemMessage(err, "Couldn't switch the flag.") });
    } finally {
      setBusyKey(null);
    }
  }

  if (load.error) {
    return (
      <ErrorPanel
        message={problemMessage(load.error, "Couldn't load the flags.")}
        onRetry={load.reload}
      />
    );
  }
  if (!load.data) return <LoadingPanel label="Loading the flags…" rows={5} />;

  return (
    <div className="flex flex-col gap-3.5">
      <p className="text-small text-muted">
        Switch features on or off without a new release. Each change is saved at once and written to
        the audit log.
      </p>
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <ul className="flex flex-col gap-2.5">
        {load.data.map((flag) => {
          const title = flag.title;
          // The API says, for this viewer and now, whether the flag can be switched and why not.
          const blocker = flag.can_switch
            ? null
            : (flag.cannot_switch_reason ?? flag.who_can_switch);
          const reasonId = `flag-${flag.key}-reason`;
          return (
            <li
              key={flag.key}
              className="flex flex-wrap items-center gap-4 rounded-card border border-line-strong bg-noir-700 px-4 py-3.5"
            >
              <div className="flex min-w-0 flex-[1_1_280px] flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-2">
                  <strong className="text-ivory">{title}</strong>
                  <code className="rounded-md border border-line bg-noir-900 px-1.5 text-xs text-gold-300">
                    {flag.key}
                  </code>
                </span>
                <span className="text-caption text-muted">{flag.description}</span>
                <span className="text-xs text-muted">{flag.who_can_switch}</span>
                {blocker && !flag.is_locked ? (
                  <span id={reasonId} className="text-caption text-body">
                    {blocker}
                    {flag.key === "admin_2fa" &&
                    me.role === "super_admin" &&
                    !me.two_factor_enabled ? (
                      <>
                        {" "}
                        <Link href={ACCOUNT_PATH} className="font-bold underline">
                          Open My account
                        </Link>
                      </>
                    ) : null}
                  </span>
                ) : null}
                {flag.updated_by && flag.updated_at ? (
                  <span className="text-xs text-muted">
                    Last switched by {flag.updated_by.name}, {formatDateTime(flag.updated_at)}
                  </span>
                ) : null}
              </div>
              {flag.is_locked ? (
                <span className="text-caption font-bold whitespace-nowrap text-muted">
                  Off · not built yet
                </span>
              ) : (
                <Switch
                  checked={flag.enabled}
                  disabled={blocker !== null}
                  busy={busyKey === flag.key}
                  onChange={(on) => void flip(flag, on)}
                  label={title}
                  stateText={{ on: "On", off: "Off" }}
                  aria-describedby={blocker ? reasonId : undefined}
                />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

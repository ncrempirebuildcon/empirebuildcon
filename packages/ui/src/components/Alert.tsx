/**
 * Inline message for form results and page states.
 *
 * - `error` uses role="alert" (announced immediately); `info` and `success` use role="status"
 *   (polite), matching handbook/DESIGN_SYSTEM.md §8 "States".
 */
import type { ReactNode } from "react";
import { cx } from "../cx";

export type AlertTone = "info" | "success" | "error";

const tones: Record<AlertTone, string> = {
  info: "border-gold-line-strong text-body",
  success: "border-palm-line text-palm",
  error: "border-danger text-danger",
};

export interface AlertProps {
  tone?: AlertTone;
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Alert({ tone = "info", title, children, className }: AlertProps) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cx("rounded-tile border bg-noir-800 px-4 py-3 text-small", tones[tone], className)}
    >
      {title ? <p className="mb-1 font-bold">{title}</p> : null}
      <div>{children}</div>
    </div>
  );
}

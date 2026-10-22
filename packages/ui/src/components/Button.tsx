/**
 * Button: the four button styles from handbook/DESIGN_SYSTEM.md §8 (primary, secondary,
 * tertiary, WhatsApp), with loading and disabled states.
 *
 * Accessibility (WCAG 2.1 AA, DESIGN_SYSTEM §9):
 * - Min height 44 px (touch target) except `tertiary`, which is an inline text action.
 * - Loading keeps the label visible and sets `aria-busy`; the click is ignored meanwhile.
 * - Disabled uses `aria-disabled` instead of the `disabled` attribute so the button stays
 *   focusable and screen readers can still announce it.
 *
 * Use `buttonClasses()` to style a link (`<a>` / Next `<Link>`) as a button.
 */
import type { ButtonHTMLAttributes, MouseEvent, ReactNode } from "react";
import { cx } from "../cx";

export type ButtonVariant = "primary" | "secondary" | "tertiary" | "whatsapp";

const base =
  "inline-flex items-center justify-center gap-2 rounded-pill font-sans text-small " +
  "transition-colors duration-150 ease-brand select-none";

const variants: Record<ButtonVariant, string> = {
  primary: "min-h-11 px-5 bg-gold-500 text-noir-900 font-extrabold hover:bg-gold-400",
  secondary: "min-h-11 px-5 border border-gold-500 text-gold-300 font-bold hover:bg-gold-tint",
  tertiary: "px-1 text-gold-400 font-bold underline-offset-4 hover:underline",
  whatsapp: "min-h-11 px-5 bg-palm-bg text-palm font-bold hover:brightness-110",
};

/** Class string for a link that should look like a button. */
export function buttonClasses(variant: ButtonVariant = "primary", extra?: string): string {
  return cx(base, variants[variant], extra);
}

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "disabled"> {
  variant?: ButtonVariant;
  /** Shows a spinner, keeps the label, and ignores clicks until it is false again. */
  loading?: boolean;
  /** Announced as disabled but stays focusable (aria-disabled). */
  disabled?: boolean;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  loading = false,
  disabled = false,
  type = "button",
  className,
  onClick,
  children,
  ...rest
}: ButtonProps) {
  const inactive = loading || disabled;
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    // WHY: aria-disabled does not stop clicks or form submits by itself.
    if (inactive) {
      event.preventDefault();
      return;
    }
    onClick?.(event);
  };
  return (
    <button
      {...rest}
      type={type}
      aria-disabled={inactive || undefined}
      aria-busy={loading || undefined}
      onClick={handleClick}
      className={cx(buttonClasses(variant), inactive && "cursor-not-allowed opacity-45", className)}
    >
      {loading ? <Spinner /> : null}
      <span>{children}</span>
    </button>
  );
}

function Spinner() {
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      className="animate-spin motion-reduce:animate-none"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.3"
        strokeWidth="3"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

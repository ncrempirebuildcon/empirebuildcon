/**
 * Picking files: `FileDropZone` (the media manager's "Drag files here or browse" area, board
 * NoirCmsProject) and `FileButton` (a single "Upload QR image"-style button).
 *
 * How it works:
 *   1. Both draw a real <button>; clicking it opens the browser's file chooser through a hidden
 *      <input type="file">. Keyboard and screen-reader users never need to drag anything
 *      (WCAG 2.1.1 Keyboard).
 *   2. `FileDropZone` also accepts files dropped anywhere on it (a bonus for mouse users). A drag
 *      counter keeps the highlight steady while the pointer crosses child elements.
 *   3. The chosen files go to `onFiles` as an array. The input is cleared afterwards, so choosing
 *      the same file again (e.g. after a failed upload) still fires.
 *
 * `accept` only steers the chooser; callers must still check each file's type and size, because
 * dropped files and "All files" in the chooser bypass it.
 */
import { useId, useRef, useState, type DragEvent, type ReactNode, type RefObject } from "react";
import { cx } from "../cx";
import { Button, type ButtonVariant } from "./Button";

function filesOf(list: FileList | null | undefined): File[] {
  return list ? Array.from(list) : [];
}

function HiddenInput({
  inputRef,
  accept,
  multiple,
  onFiles,
}: {
  inputRef: RefObject<HTMLInputElement | null>;
  accept?: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
}) {
  return (
    <input
      ref={inputRef}
      type="file"
      hidden
      accept={accept}
      multiple={multiple}
      onChange={(event) => {
        const files = filesOf(event.target.files);
        event.target.value = "";
        if (files.length > 0) onFiles(files);
      }}
    />
  );
}

export interface FileDropZoneProps {
  /** Called with the chosen or dropped files. */
  onFiles: (files: File[]) => void;
  /** File types offered by the chooser, e.g. "image/*,.pdf". */
  accept?: string;
  /** Allow several files at once. Default true. */
  multiple?: boolean;
  /** Which types and sizes are allowed, in words. Linked to the button with aria-describedby. */
  hint: ReactNode;
  /** Blocks choosing and dropping (e.g. while uploads run or without permission). */
  disabled?: boolean;
  /** Id of the button, so callers can move focus back to it. */
  id?: string;
  className?: string;
}

export function FileDropZone({
  onFiles,
  accept,
  multiple = true,
  hint,
  disabled = false,
  id,
  className,
}: FileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const [dragDepth, setDragDepth] = useState(0);
  const over = dragDepth > 0 && !disabled;

  const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer.types).includes("Files");

  return (
    <div
      onDragEnter={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        setDragDepth((depth) => depth + 1);
      }}
      onDragOver={(event) => {
        if (!hasFiles(event)) return;
        // WHY: without preventDefault the browser opens the dropped file instead.
        event.preventDefault();
        event.dataTransfer.dropEffect = disabled ? "none" : "copy";
      }}
      onDragLeave={(event) => {
        if (!hasFiles(event)) return;
        setDragDepth((depth) => Math.max(0, depth - 1));
      }}
      onDrop={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        setDragDepth(0);
        if (disabled) return;
        const files = filesOf(event.dataTransfer.files);
        if (files.length > 0) onFiles(multiple ? files : files.slice(0, 1));
      }}
      className={cx(
        "flex flex-wrap items-center gap-4 rounded-tile border-[1.5px] border-dashed p-5.5",
        "transition-colors duration-150",
        over ? "border-gold-400 bg-gold-tint" : "border-gold-500/55 bg-noir-700",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="flex size-13 shrink-0 items-center justify-center rounded-tile bg-gold-tint"
      >
        <svg
          width="26"
          height="26"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          className="text-gold-400"
        >
          <path d="M12 16V4M7 9l5-5 5 5" />
          <path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
        </svg>
      </span>
      <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-0.5">
        <button
          id={id}
          type="button"
          aria-describedby={hintId}
          aria-disabled={disabled || undefined}
          onClick={() => {
            if (!disabled) inputRef.current?.click();
          }}
          className={cx(
            "min-h-11 self-start text-left text-base font-bold text-ivory",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          {over ? "Drop to upload" : "Drag files here or "}
          {over ? null : (
            <span className="font-extrabold text-gold-400 underline underline-offset-4">
              browse
            </span>
          )}
        </button>
        <div id={hintId} className="text-caption text-muted">
          {hint}
        </div>
      </div>
      <HiddenInput inputRef={inputRef} accept={accept} multiple={multiple} onFiles={onFiles} />
    </div>
  );
}

export interface FileButtonProps {
  /** Called with the chosen file(s). */
  onFiles: (files: File[]) => void;
  /** Button text, e.g. "Upload QR image". */
  children: ReactNode;
  accept?: string;
  multiple?: boolean;
  variant?: ButtonVariant;
  disabled?: boolean;
  loading?: boolean;
  id?: string;
  className?: string;
  /** Extra words for screen readers, e.g. which configuration the floor plan is for. */
  "aria-label"?: string;
  "aria-describedby"?: string;
}

/** A button that opens the file chooser (no drop area). */
export function FileButton({
  onFiles,
  children,
  accept,
  multiple = false,
  variant = "secondary",
  disabled,
  loading,
  id,
  className,
  "aria-label": ariaLabel,
  "aria-describedby": describedBy,
}: FileButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button
        id={id}
        variant={variant}
        disabled={disabled}
        loading={loading}
        className={className}
        aria-label={ariaLabel}
        aria-describedby={describedBy}
        onClick={() => inputRef.current?.click()}
      >
        {children}
      </Button>
      <HiddenInput inputRef={inputRef} accept={accept} multiple={multiple} onFiles={onFiles} />
    </>
  );
}

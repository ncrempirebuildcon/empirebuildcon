/**
 * Sending files to the media library, with progress and cancel (ARCHITECTURE §12, the sequence
 * diagram handbook/diagrams/seq-media.svg).
 *
 * Two paths, chosen by kind:
 *   - Photos: resized in the browser (resize.ts), then POSTed as multipart to
 *     /admin/media/images. The API checks magic bytes and size, uploads to the store, saves the
 *     row and attaches it, all in one request.
 *   - Videos and documents: too big to pass through the API, so they go straight to the store:
 *       1. POST /admin/media/upload-signature (kind, name, size, type) → signed fields + upload_url.
 *       2. POST the file with exactly those fields to upload_url (Cloudinary, or the fake store's
 *          Cloudinary-shaped endpoint in development and tests).
 *       3. POST /admin/media/confirm with the store's reply unmodified (the API verifies its
 *          signature and re-reads the asset), plus where to attach it.
 *
 * WHY XMLHttpRequest and not fetch: only XHR reports upload progress in every browser
 * (`xhr.upload.onprogress`); fetch has no upload progress events.
 *
 * SECURITY:
 * - Writes to our API carry the session's CSRF token (lib/api.ts keeps it in memory only).
 * - Nothing extra is sent to the store: no cookies (`withCredentials` off) and no custom headers,
 *   so the session never leaves our site and no CORS preflight is needed. Only the cloud name and
 *   API key come to the browser, inside the signature; the API secret stays on the server
 *   (SECURITY.md §7).
 */
import { ProblemError, type Problem } from "@empire/api-client";
import { api, call, currentCsrfToken, type Schema } from "@/lib/api";
import { SIGN_IN_PATH } from "@/lib/routes";
import { titleFromFileName, type MediaKind } from "./files";
import type { HonestLabel } from "./labels";
import { prepareImage, type ImageEncoding } from "./resize";

export type Media = Schema<"Media">;
export type LinkedMedia = Schema<"LinkedMedia">;
export type MediaRole = LinkedMedia["role"];

/** The owner kinds a file can be attached to (ARCHITECTURE §6, exclusive arc). */
export type OwnerType = "project" | "configuration" | "construction_update";

/**
 * The roles the CMS attaches to. WHY not "hero" and "og_image": the API refuses them; the share
 * image is the project's `seo.og_image_id` (SEO tab), and there is no hero image yet.
 */
export type AttachRole = Exclude<MediaRole, "hero" | "og_image">;

/** Where an upload is attached once saved: an owner and a role, e.g. a project's gallery. */
export interface AttachTarget {
  ownerType: OwnerType;
  ownerId: string;
  role: AttachRole;
}

/** "project:<uuid>", the API's `attach_to` format. */
export const attachTo = (target: AttachTarget) => `${target.ownerType}:${target.ownerId}`;

/** What an upload is doing now, for the progress line. */
export type UploadPhase = "preparing" | "uploading" | "saving";

export interface UploadCallbacks {
  /** Bytes sent so far and the total, while the file is being sent. */
  onProgress?: (loaded: number, total: number) => void;
  /** Called when the upload moves to another phase. */
  onPhase?: (phase: UploadPhase) => void;
  /** Aborts the upload while the file is being sent. */
  signal?: AbortSignal;
}

/** Thrown when the user cancels; callers show "Cancelled", not an error. */
export class UploadCancelled extends Error {
  constructor() {
    super("The upload was cancelled.");
    this.name = "UploadCancelled";
  }
}

const OFFLINE: Problem = {
  title: "Network error",
  status: 0,
  detail: "We couldn't reach the server. Check your connection and try again.",
};

interface XhrResult {
  status: number;
  body: unknown;
}

/** POSTs a multipart form with progress; resolves with the status and the parsed JSON body. */
function postForm(
  url: string,
  form: FormData,
  options: UploadCallbacks & { headers?: Record<string, string>; withCredentials: boolean },
): Promise<XhrResult> {
  return new Promise((resolve, reject) => {
    if (options.signal?.aborted) {
      reject(new UploadCancelled());
      return;
    }
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.withCredentials = options.withCredentials;
    for (const [name, value] of Object.entries(options.headers ?? {})) {
      xhr.setRequestHeader(name, value);
    }
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) options.onProgress?.(event.loaded, event.total);
    };
    // Every byte has left the browser: from here the server (or store) finishes on its own,
    // so the upload moves to "saving" and can no longer be cancelled (useUploads).
    xhr.upload.onload = () => options.onPhase?.("saving");
    const onAbort = () => xhr.abort();
    options.signal?.addEventListener("abort", onAbort, { once: true });
    const done = () => options.signal?.removeEventListener("abort", onAbort);
    xhr.onload = () => {
      done();
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }
      resolve({ status: xhr.status, body });
    };
    xhr.onerror = () => {
      done();
      reject(new ProblemError(OFFLINE));
    };
    xhr.onabort = () => {
      done();
      reject(new UploadCancelled());
    };
    xhr.send(form);
  });
}

/** The problem for an error reply from our API (problem+json) or a generic one. */
function problemFrom(result: XhrResult, fallback: string): ProblemError {
  const body = result.body as Partial<Problem> | null;
  if (body && typeof body.status === "number" && typeof body.title === "string") {
    return new ProblemError(body as Problem);
  }
  return new ProblemError({ title: fallback, status: result.status, detail: fallback });
}

export interface PhotoOptions {
  target?: AttachTarget;
  title?: string;
  altText?: string;
  /** The honest label to save with the photo, when the place says what it is. */
  label?: HonestLabel;
  /** First day of the month the photo shows (required with "progress_photo"). */
  labelMonth?: string;
  /** How to encode it in the browser: "photo" (default), "qr" or "plan" (resize.ts). */
  encoding?: ImageEncoding;
}

/**
 * Resizes and uploads one photo through the API, optionally attaching it.
 *
 * @throws ProblemError (refused by the API, e.g. 413 or 415), UploadCancelled.
 */
export async function uploadPhoto(
  file: File,
  options: PhotoOptions,
  callbacks: UploadCallbacks = {},
): Promise<Media> {
  callbacks.onPhase?.("preparing");
  const prepared = await prepareImage(file, options.encoding);
  if (callbacks.signal?.aborted) throw new UploadCancelled();

  const form = new FormData();
  form.append("file", prepared.file, prepared.file.name);
  form.append("title", options.title ?? titleFromFileName(file.name));
  if (options.altText) form.append("alt_text", options.altText);
  if (options.label) form.append("label", options.label);
  if (options.labelMonth) form.append("label_month", options.labelMonth);
  if (options.target) {
    form.append("attach_to", attachTo(options.target));
    form.append("role", options.target.role);
  }
  callbacks.onPhase?.("uploading");
  const token = currentCsrfToken();
  const result = await postForm("/api/v1/admin/media/images", form, {
    ...callbacks,
    withCredentials: true,
    headers: token ? { "X-CSRF-Token": token } : {},
  });
  if (result.status === 401) window.location.assign(SIGN_IN_PATH);
  if (result.status < 200 || result.status >= 300) {
    throw problemFrom(result, "Couldn't upload the photo.");
  }
  return result.body as Media;
}

export interface DirectOptions {
  kind: Exclude<MediaKind, "image">;
  /** The checked MIME type (files.ts `checkFile`). */
  mimeType: string;
  target?: AttachTarget;
  title?: string;
}

/**
 * Uploads a video or document straight to the store, then saves it through the API.
 *
 * @throws ProblemError (the API or the store refused it), UploadCancelled.
 */
export async function uploadDirect(
  file: File,
  options: DirectOptions,
  callbacks: UploadCallbacks = {},
): Promise<Media> {
  callbacks.onPhase?.("preparing");
  const signed = await call(
    api.POST("/api/v1/admin/media/upload-signature", {
      body: {
        kind: options.kind,
        filename: shortFileName(file.name),
        bytes: file.size,
        mime_type: options.mimeType,
      },
    }),
  ); // 1
  if (callbacks.signal?.aborted) throw new UploadCancelled();

  // INVARIANT: exactly the fields the API signed go to the store, unchanged, plus the file.
  // Anything added or changed breaks the signature: Cloudinary signs every parameter except
  // file, cloud_name, resource_type and api_key (cloudinary.com/documentation/authentication_signatures).
  const form = new FormData();
  for (const [name, value] of Object.entries(signed.fields)) form.append(name, value);
  form.append("file", file, file.name);

  callbacks.onPhase?.("uploading");
  const reply = await postForm(signed.upload_url, form, { ...callbacks, withCredentials: false }); // 2
  if (reply.status < 200 || reply.status >= 300 || reply.body === null) {
    throw storeProblem(reply);
  }

  callbacks.onPhase?.("saving");
  return call(
    api.POST("/api/v1/admin/media/confirm", {
      body: {
        cloudinary_response: reply.body as Record<string, unknown>,
        title: options.title ?? titleFromFileName(file.name),
        attach_to: options.target ? attachTo(options.target) : null,
        role: options.target?.role ?? null,
      },
    }),
  ); // 3
}

/**
 * The file name for the upload signature, at most 200 characters (the API's limit), keeping the
 * extension: the API reads the type from it, so cutting it off would get a 415.
 */
export function shortFileName(name: string, max = 200): string {
  if (name.length <= max) return name;
  const dot = name.lastIndexOf(".");
  const extension = dot > 0 && name.length - dot <= 10 ? name.slice(dot) : "";
  return name.slice(0, max - extension.length) + extension;
}

/** A sentence for a refusal from the store (Cloudinary answers {"error": {"message": …}}). */
function storeProblem(reply: XhrResult): ProblemError {
  const body = reply.body as { error?: { message?: unknown } } | null;
  const message = typeof body?.error?.message === "string" ? body.error.message : null;
  if (reply.status === 0) return new ProblemError(OFFLINE);
  return new ProblemError({
    title: "Upload refused",
    status: reply.status >= 400 && reply.status < 500 ? 422 : reply.status || 502,
    detail: message
      ? `The file store refused the file: ${message}`
      : "The file store didn't accept the file. Please try again.",
  });
}

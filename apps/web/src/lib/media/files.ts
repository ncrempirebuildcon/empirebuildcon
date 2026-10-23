/**
 * Which files the media manager accepts, where each one goes, and the sentence shown when one is
 * refused. Checked in the browser before anything is uploaded, so staff hear "too big" at once
 * instead of after a long upload.
 *
 * Collaborators: upload.ts (sends the file), resize.ts (photos), the API's media module (which
 * checks everything again: magic bytes, size, type; SECURITY.md §6).
 * Implements: ARCHITECTURE §12 (photos through the API, videos and documents direct), the board
 * NoirCmsProject drop-zone text, D-007 (Cloudinary Free plan limits).
 *
 * SECURITY: these checks are for the user's convenience only. The API never trusts the browser's
 * type or size; it re-reads both (magic bytes for photos, the store's own record for direct
 * uploads) before saving.
 */

/** What a file becomes in the library. */
export type MediaKind = "image" | "video" | "document";

/** Bytes in one megabyte, as the limits below and Cloudinary's plan page count them. */
export const MB = 1024 * 1024;

/**
 * Upload limits per kind (ARCHITECTURE §12, Cloudinary Free: 10 MB images and raw files, 100 MB
 * video). WHY here as well as in the API: to refuse a file before uploading it. The API's
 * `max_bytes` in an upload signature wins for direct uploads (upload.ts reads it).
 */
export const MAX_BYTES: Record<MediaKind, number> = {
  image: 10 * MB,
  video: 100 * MB,
  document: 10 * MB,
};

interface Accepted {
  kind: MediaKind;
  /** Extensions without the dot, lower case. */
  extensions: readonly string[];
  mimeTypes: readonly string[];
}

// SECURITY: no SVG (script risk), no HEIC or GIF (SECURITY.md §6); the API refuses them too.
const ACCEPTED: readonly Accepted[] = [
  {
    kind: "image",
    extensions: ["jpg", "jpeg", "png", "webp", "avif"],
    mimeTypes: ["image/jpeg", "image/png", "image/webp", "image/avif"],
  },
  {
    kind: "video",
    extensions: ["mp4", "mov", "webm"],
    mimeTypes: ["video/mp4", "video/quicktime", "video/webm"],
  },
  {
    kind: "document",
    extensions: ["pdf", "doc", "docx", "ppt", "pptx"],
    mimeTypes: [
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "application/vnd.ms-powerpoint",
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ],
  },
];

/** The `accept` attribute for a file chooser offering these kinds. */
export function acceptFor(kinds: readonly MediaKind[]): string {
  return ACCEPTED.filter((a) => kinds.includes(a.kind))
    .flatMap((a) => [...a.mimeTypes, ...a.extensions.map((e) => `.${e}`)])
    .join(",");
}

/** The chooser filter for a PDF only (the brochure). */
export const ACCEPT_PDF = "application/pdf,.pdf";

const extensionOf = (name: string) => name.split(".").pop()?.toLowerCase() ?? "";

/** "4.2 MB", "820 KB": sizes in the units staff see on their computer. */
export function formatBytes(bytes: number): string {
  if (bytes >= MB) return `${(bytes / MB).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** What a chosen file is, or why it can't be uploaded. */
export type FileCheck =
  { ok: true; kind: MediaKind; mimeType: string } | { ok: false; message: string };

const REFUSED_TYPES: Record<string, string> = {
  svg: "SVG files can't be uploaded, because they can carry scripts. Export the image as PNG.",
  heic: "HEIC photos (from an iPhone) can't be used on the website. Export them as JPEG first.",
  heif: "HEIC photos (from an iPhone) can't be used on the website. Export them as JPEG first.",
  gif: "GIF images can't be uploaded. Use JPEG, PNG, WebP or AVIF.",
};

/**
 * Checks one file's type (by extension and, when the browser knows it, MIME type) and size.
 *
 * WHY both: Windows often reports "" or a generic type for Office files, and a renamed file has
 * the wrong extension. A file passes when either matches a kind and neither points elsewhere.
 *
 * @param only Restrict to these kinds (e.g. the RERA QR takes images only).
 */
export function checkFile(file: File, only?: readonly MediaKind[]): FileCheck {
  const extension = extensionOf(file.name);
  const mime = file.type.toLowerCase();
  const refused = REFUSED_TYPES[extension] ?? (mime === "image/svg+xml" ? REFUSED_TYPES.svg : null);
  if (refused) return { ok: false, message: `${file.name}: ${refused}` };

  const byMime = ACCEPTED.find((a) => a.mimeTypes.includes(mime));
  const byExtension = ACCEPTED.find((a) => a.extensions.includes(extension));
  const match =
    byMime && byExtension ? (byMime === byExtension ? byMime : undefined) : (byMime ?? byExtension);
  if (!match || (only && !only.includes(match.kind))) {
    return { ok: false, message: `${file.name}: ${typeHelp(only)}` };
  }
  if (file.size === 0) return { ok: false, message: `${file.name} is empty.` };
  if (file.size > MAX_BYTES[match.kind]) {
    return {
      ok: false,
      message: `${file.name} is ${formatBytes(file.size)}. ${KIND_NAME[match.kind]} can be up to ${formatBytes(MAX_BYTES[match.kind])}.`,
    };
  }
  const mimeType = byMime === match ? mime : (MIME_BY_EXTENSION[extension] ?? mime);
  return { ok: true, kind: match.kind, mimeType };
}

/** The MIME type to declare when the browser didn't report one (or reported a generic one). */
const MIME_BY_EXTENSION: Record<string, string> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  avif: "image/avif",
  mp4: "video/mp4",
  mov: "video/quicktime",
  webm: "video/webm",
  pdf: "application/pdf",
  doc: "application/msword",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ppt: "application/vnd.ms-powerpoint",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
};

const KIND_NAME: Record<MediaKind, string> = {
  image: "Photos",
  video: "Videos",
  document: "Documents",
};

function typeHelp(only?: readonly MediaKind[]): string {
  const kinds = only ?? (["image", "video", "document"] as const);
  const parts: string[] = [];
  if (kinds.includes("image")) parts.push("photos as JPG, PNG, WebP or AVIF");
  if (kinds.includes("video")) parts.push("videos as MP4, MOV or WebM");
  if (kinds.includes("document")) parts.push("documents as PDF, DOC, DOCX, PPT or PPTX");
  return `this type of file can't be uploaded here. Use ${parts.join("; ")}.`;
}

/** The drop zone's line about types and sizes (board NoirCmsProject). */
export const DROP_ZONE_HINT =
  "Photos: JPG, PNG, WebP, AVIF up to 10 MB · Videos: MP4, MOV, WebM up to 100 MB · Documents: PDF, DOC, PPT up to 10 MB. Each file goes to the right list by type.";

/** A title from a file name: "tower-a_night.jpg" → "tower a night". Staff can rename it. */
export function titleFromFileName(name: string): string {
  const base = name.replace(/\.[^.]+$/, "");
  const cleaned = base.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return (cleaned || "Untitled").slice(0, 160);
}

/** True for a PDF, by type or extension (the brochure and PDF floor plans). */
export function isPdf(file: File): boolean {
  return file.type === "application/pdf" || extensionOf(file.name) === "pdf";
}

/** True for a photo type the media manager accepts (JPG, PNG, WebP, AVIF), by type or extension. */
export function isImage(file: File): boolean {
  const image = ACCEPTED.find((a) => a.kind === "image");
  return Boolean(
    image &&
    (image.mimeTypes.includes(file.type.toLowerCase()) ||
      image.extensions.includes(extensionOf(file.name))),
  );
}

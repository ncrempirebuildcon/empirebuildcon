/**
 * Prepares an image in the browser before it is uploaded (ARCHITECTURE §12), in one of three
 * encodings chosen by where the image goes:
 *   - "photo" (gallery, progress photos, share image): long edge 2560 px, WebP at quality 0.85,
 *     or JPEG at 0.85 where the browser can't write WebP.
 *   - "qr" (the RERA QR code): lossless PNG, long edge 1200 px, which is plenty to scan and keeps
 *     the file small.
 *   - "plan" (floor plans, which are line drawings): lossless WebP, or PNG where the browser
 *     can't write lossless WebP, long edge 2560 px.
 *
 * How it works:
 *   1. Decode the file with createImageBitmap, honouring the camera's rotation (EXIF orientation).
 *   2. For each allowed long edge, largest first (never enlarging): draw onto a canvas and encode.
 *   3. Keep the first result at or under the 10 MB upload cap; lossless encodings of big scans
 *      can exceed it, so a smaller size is tried next.
 *   4. WebP falls back when the browser returns another type (it gives PNG when it can't encode
 *      WebP); "plan" also checks the WebP is really lossless (a VP8L chunk), else uses PNG.
 *      JPEG is drawn on white because it has no transparency.
 *
 * WHY always re-encode, even small images: drawing to a canvas drops the file's EXIF data,
 * including the GPS position phones store, before the file leaves the staff member's computer.
 * The API strips metadata again (SECURITY.md §6); this is the first line.
 *
 * When the browser can't decode the file (e.g. AVIF in an old browser), or no size fits, the
 * original file is sent unchanged: the API still checks it (magic bytes, 10 MB, 25 MP).
 */
import { MAX_BYTES } from "./files";

/** How an image is encoded before upload (see the file header). */
export type ImageEncoding = "photo" | "qr" | "plan";

/** Long edges tried for each encoding, largest first. */
const EDGES: Record<ImageEncoding, readonly number[]> = {
  photo: [2560, 2048, 1600],
  qr: [1200, 900, 600],
  plan: [2560, 2048, 1600, 1200],
};

/** Long edge of a photo after resizing, in pixels of the source image. */
export const MAX_EDGE_PX = 2560;
/** Encoder quality for lossy WebP and JPEG (0–1). */
export const QUALITY = 0.85;

export interface PreparedImage {
  /** The file to upload (resized and re-encoded, or the original when that wasn't possible). */
  file: File;
  width: number | null;
  height: number | null;
  /** False when the original was sent as is. */
  reencoded: boolean;
}

/** New width and height so the long edge is at most `maxEdge` (never enlarged). */
export function fitWithin(
  width: number,
  height: number,
  maxEdge = MAX_EDGE_PX,
): { width: number; height: number } {
  const longEdge = Math.max(width, height);
  if (longEdge <= maxEdge) return { width, height };
  const scale = maxEdge / longEdge;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

type AnyCanvas = HTMLCanvasElement | OffscreenCanvas;

function makeCanvas(width: number, height: number): AnyCanvas {
  if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(width, height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function encode(canvas: AnyCanvas, type: string, quality?: number): Promise<Blob | null> {
  if ("convertToBlob" in canvas) {
    return canvas.convertToBlob({ type, quality }).catch(() => null);
  }
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

function draw(
  bitmap: ImageBitmap,
  width: number,
  height: number,
  background?: string,
): AnyCanvas | null {
  const canvas = makeCanvas(width, height);
  const context = canvas.getContext("2d") as
    CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D | null;
  if (!context) return null;
  if (background) {
    context.fillStyle = background;
    context.fillRect(0, 0, width, height);
  }
  context.imageSmoothingQuality = "high";
  context.drawImage(bitmap, 0, 0, width, height);
  return canvas;
}

/**
 * True when a WebP file holds a lossless (VP8L) image.
 *
 * How it works: walk the RIFF chunks after the 12-byte header (VP8X, ICCP, ALPH, …), each an
 * ASCII tag, a little-endian size and the data padded to an even length, until the image chunk:
 * "VP8L" is lossless, "VP8 " is lossy.
 * WHY: the canvas API only takes a quality hint; Chromium writes lossless WebP at quality 1
 * (checked 23 Oct 2026 in the suite's Chromium), other browsers may write high-quality lossy.
 */
async function isLosslessWebp(blob: Blob): Promise<boolean> {
  const view = new DataView(await blob.arrayBuffer());
  let offset = 12;
  while (offset + 8 <= view.byteLength) {
    const tag = String.fromCharCode(
      view.getUint8(offset),
      view.getUint8(offset + 1),
      view.getUint8(offset + 2),
      view.getUint8(offset + 3),
    );
    if (tag === "VP8L") return true;
    if (tag === "VP8 ") return false;
    const size = view.getUint32(offset + 4, true);
    offset += 8 + size + (size % 2);
  }
  return false;
}

interface Encoded {
  blob: Blob;
  extension: string;
}

/** Encodes one canvas in the chosen encoding, or null when the browser can't. */
async function encodeAs(
  bitmap: ImageBitmap,
  width: number,
  height: number,
  encoding: ImageEncoding,
): Promise<Encoded | null> {
  const canvas = draw(bitmap, width, height);
  if (!canvas) return null;
  if (encoding === "plan") {
    const webp = await encode(canvas, "image/webp", 1);
    if (webp?.type === "image/webp" && (await isLosslessWebp(webp))) {
      return { blob: webp, extension: "webp" };
    }
  }
  if (encoding === "qr" || encoding === "plan") {
    const png = await encode(canvas, "image/png");
    return png?.type === "image/png" ? { blob: png, extension: "png" } : null;
  }
  const webp = await encode(canvas, "image/webp", QUALITY);
  if (webp?.type === "image/webp") return { blob: webp, extension: "webp" };
  // WHY white: JPEG has no transparency; a transparent PNG would otherwise turn black.
  const flat = draw(bitmap, width, height, "white");
  const jpeg = flat ? await encode(flat, "image/jpeg", QUALITY) : null;
  return jpeg?.type === "image/jpeg" ? { blob: jpeg, extension: "jpg" } : null;
}

const renamed = (name: string, extension: string) => `${name.replace(/\.[^.]+$/, "")}.${extension}`;

/**
 * Resizes and re-encodes one image (see the file header).
 *
 * @param encoding "photo" (default), "qr" or "plan".
 */
export async function prepareImage(
  file: File,
  encoding: ImageEncoding = "photo",
): Promise<PreparedImage> {
  const original: PreparedImage = { file, width: null, height: null, reencoded: false };
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" }); // 1
  } catch {
    return original;
  }
  try {
    const tried = new Set<string>();
    for (const edge of EDGES[encoding]) {
      const { width, height } = fitWithin(bitmap.width, bitmap.height, edge); // 2
      const size = `${width}x${height}`;
      if (tried.has(size)) continue;
      tried.add(size);
      const encoded = await encodeAs(bitmap, width, height, encoding); // 4
      if (!encoded) return original;
      if (encoded.blob.size <= MAX_BYTES.image) {
        // 3
        return {
          file: new File([encoded.blob], renamed(file.name, encoded.extension), {
            type: encoded.blob.type,
          }),
          width,
          height,
          reencoded: true,
        };
      }
    }
    return original;
  } finally {
    bitmap.close();
  }
}

/**
 * Small files made inside the tests (a PNG and a PDF), so the media journeys need no binary
 * fixtures in git (spec Phase 4 part 2 §4: "generated in the test, no binary fixtures over a few
 * KB").
 *
 * Both are real, valid files: the API checks a photo's magic bytes and reads its size, and the
 * browser decodes the PNG to resize it before upload. They carry the word SAMPLE where it shows,
 * so nothing here could pass for a real photo or document (CODE_STYLE §7).
 */
import { crc32, deflateSync } from "node:zlib";

/** A file for Playwright's `setFiles` / `setInputFiles`. */
export interface TestFile {
  name: string;
  mimeType: string;
  buffer: Buffer;
}

function chunk(type: string, data: Buffer): Buffer {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

/**
 * A width × height RGB PNG; `pixel(x, y)` gives each pixel's colour.
 * Format: PNG signature, IHDR (8-bit RGB), one IDAT of filter-0 rows, IEND (ISO/IEC 15948).
 */
export function pngBuffer(
  width: number,
  height: number,
  pixel: (x: number, y: number) => [number, number, number],
): Buffer {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header.writeUInt8(8, 8); // bit depth
  header.writeUInt8(2, 9); // colour type: RGB
  const rows = Buffer.alloc(height * (1 + width * 3));
  for (let y = 0; y < height; y += 1) {
    const row = y * (1 + width * 3);
    rows[row] = 0; // filter: none
    for (let x = 0; x < width; x += 1) {
      const [r, g, b] = pixel(x, y);
      rows.set([r, g, b], row + 1 + x * 3);
    }
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(rows)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

/** A plain photo stand-in: a gold-to-dark gradient tile (clearly not a real photo). */
export function samplePhoto(name: string, shade = 0): TestFile {
  const buffer = pngBuffer(64, 48, (x, y) => [
    Math.min(255, 120 + x + shade),
    Math.min(255, 80 + y + shade),
    40,
  ]);
  return { name, mimeType: "image/png", buffer };
}

/** A QR-like black and white pattern on a quiet zone (not a real QR code). */
export function sampleQr(name = "SAMPLE-rera-qr.png"): TestFile {
  const size = 64;
  const buffer = pngBuffer(size, size, (x, y) => {
    const inside = x >= 8 && y >= 8 && x < size - 8 && y < size - 8;
    const dark = inside && ((x >> 2) + (y >> 2)) % 2 === 0;
    return dark ? [0, 0, 0] : [255, 255, 255];
  });
  return { name, mimeType: "image/png", buffer };
}

/** A one-page PDF that says "SAMPLE document" (offsets in the xref table are computed). */
export function samplePdf(name = "SAMPLE-specifications.pdf"): TestFile {
  const stream = "BT /F1 18 Tf 24 60 Td (SAMPLE document) Tj ET";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 240 120] /Contents 4 0 R " +
      "/Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(body, "latin1"));
    body += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(body, "latin1");
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) body += `${String(offset).padStart(10, "0")} 00000 n \n`;
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return { name, mimeType: "application/pdf", buffer: Buffer.from(body, "latin1") };
}

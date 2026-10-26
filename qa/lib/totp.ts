/**
 * Authenticator codes for the two-factor journey (RFC 6238 TOTP: HMAC-SHA1, 30-second steps,
 * 6 digits), computed in the test from the key the set-up screen shows, like a phone app would.
 * Node's own crypto only; no dependency.
 *
 * SECURITY: the key belongs to a throwaway account made in the run; it is never written to disk.
 */
import { createHmac } from "node:crypto";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

/** Bytes of a base32 key as authenticator apps accept it (spaces, dashes and case ignored). */
export function base32Decode(key: string): Buffer {
  const clean = key.toUpperCase().replace(/[\s-]/g, "").replace(/=+$/, "");
  let bits = 0;
  let value = 0;
  const out: number[] = [];
  for (const char of clean) {
    const index = ALPHABET.indexOf(char);
    if (index < 0) throw new Error("The key is not base32.");
    value = (value << 5) | index;
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(out);
}

/** The HOTP value for one counter (RFC 4226 §5.3), as `digits` digits. */
export function hotp(secret: Buffer, counter: number, digits = 6): string {
  const message = Buffer.alloc(8);
  message.writeBigUInt64BE(BigInt(counter));
  const mac = createHmac("sha1", secret).update(message).digest();
  const offset = (mac[mac.length - 1] ?? 0) & 0x0f;
  const binary =
    (((mac[offset] ?? 0) & 0x7f) << 24) |
    ((mac[offset + 1] ?? 0) << 16) |
    ((mac[offset + 2] ?? 0) << 8) |
    (mac[offset + 3] ?? 0);
  return String(binary % 10 ** digits).padStart(digits, "0");
}

/** The 30-second step of a time (RFC 6238 T0 = 0). */
export function timeStep(atMs: number = Date.now()): number {
  return Math.floor(atMs / 1000 / 30);
}

/** The code an authenticator app shows for `key` at `atMs` (default now). */
export function totp(key: string, atMs: number = Date.now()): string {
  return hotp(base32Decode(key), timeStep(atMs));
}

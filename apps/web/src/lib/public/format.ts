/**
 * Public site formatting and URL helpers (Phase 5 Task 5.2).
 *
 * Implements ARCHITECTURE §15, DESIGN_SYSTEM & D-038:
 *   - WhatsApp links format phone digits and replace `{page}` with current path.
 *   - Tel links strip non-dialable characters.
 *   - Placeholders in `[brackets]` are hidden in production.
 */

export function isPlaceholder(val: string | null | undefined): boolean {
  if (!val) return true;
  const trimmed = val.trim();
  return trimmed.startsWith("[") && trimmed.endsWith("]");
}

export function isProductionEnv(): boolean {
  return process.env.APP_ENV === "production";
}

export function filterPlaceholders(
  items: (string | null | undefined)[],
  isProduction: boolean = isProductionEnv(),
): string[] {
  return items.filter((item): item is string => {
    if (!item || !item.trim()) return false;
    if (isProduction && isPlaceholder(item)) return false;
    return true;
  });
}

export function filterValue(
  value: string | null | undefined,
  isProduction: boolean = isProductionEnv(),
): string | null {
  if (!value || !value.trim()) return null;
  if (isProduction && isPlaceholder(value)) return null;
  return value.trim();
}

export function formatWhatsAppDigits(phone: string): string {
  return phone.replace(/\D/g, "");
}

export function buildWhatsAppLink(
  phone: string | null | undefined,
  template: string | null | undefined,
  pagePath: string,
  isProduction: boolean = isProductionEnv(),
): string | null {
  const effectivePhone = filterValue(phone, isProduction);
  if (!effectivePhone) return null;

  const digits = formatWhatsAppDigits(effectivePhone);
  if (!digits) return null;

  const effectiveTemplate =
    filterValue(template, isProduction) ?? "Hello, I am enquiring about {page}";
  const message = effectiveTemplate.replace(/{page}/g, pagePath);

  return `https://wa.me/${digits}?text=${encodeURIComponent(message)}`;
}

export function buildTelLink(
  phone: string | null | undefined,
  isProduction: boolean = isProductionEnv(),
): string | null {
  const effectivePhone = filterValue(phone, isProduction);
  if (!effectivePhone) return null;

  const dialable = effectivePhone.replace(/[^\d+]/g, "");
  if (!dialable) return null;

  return `tel:${dialable}`;
}

/**
 * /admin/catalogue: cities, localities and amenities that projects choose from.
 * Session checked on the server; lists loaded in the browser (ARCHITECTURE.md §5).
 */
import type { Metadata } from "next";
import { requireSessionUser } from "@/lib/session";
import { AdminShell } from "../AdminShell";
import { CatalogueScreen } from "./CatalogueScreen";

export const metadata: Metadata = { title: "Catalogue" };
export const dynamic = "force-dynamic";

export default async function CataloguePage() {
  const me = await requireSessionUser();
  return (
    <AdminShell me={me} section="catalogue" heading="Catalogue">
      <CatalogueScreen />
    </AdminShell>
  );
}

/**
 * The lead writes more than one screen sends (lead detail, pipeline board), so each request is
 * written once. Reads stay next to the screen that shows them.
 */
import { api, call, type Schema } from "../api";
import type { Lead } from "./labels";

/** PATCH /admin/leads/{id} with only what changes (LeadUpdate). Owner changes need leads.assign. */
export function updateLead(id: string, body: Schema<"LeadUpdate">): Promise<Lead> {
  return call(api.PATCH("/api/v1/admin/leads/{id}", { params: { path: { id } }, body }));
}

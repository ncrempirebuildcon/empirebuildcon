"""Leads module (Phase 4 part 3): public intake, the lead inbox and pipeline, notes and activity,
site visits, CSV export, the UTM report, erasure and retention (ARCHITECTURE §8).

Layout (CODE_STYLE §4):
  - `vocab.py` (allowed values), `phone.py` (Indian numbers → E.164), `reference.py` (EMP-XXXXX)
  - `models.py` (tables of 0004_leads), `schemas.py` / `schemas_public.py` (shapes),
    `fields.py` (bounded field types)
  - `access.py` (who sees which lead: SECURITY.md §1), `routing.py` (who gets a new lead),
    `filters.py` (inbox filters → SQL, shared with the export)
  - `intake.py` (public enquiries, site-visit and brochure requests), `creation.py` (the new
    row, its consent and the duplicate link), `effects.py` (activity, audit and outbox helpers
    shared by every writer)
  - `service.py` (inbox, detail, pipeline, notes, manual leads), `visits.py` (site visits),
    `export.py` (CSV), `report.py` (UTM counts), `erasure.py` (erase and retention)
  - `present.py` (rows → responses), `queries.py` (what other modules call)
  - `routes_public.py`, `routes.py`, `routes_visits.py` (HTTP only), `seed.py` (sample leads)

Implements: ARCHITECTURE §6 (lead indexes, deletion), §8, §9 (lead.* and site_visit.* events),
§10 (retention in the clean-up), §11 (leads.* and site_visits.manage); SECURITY.md §1, §2, §8;
D-016 (routing, site visits), D-017 (consent texts are drafts until the owner approves them).
"""

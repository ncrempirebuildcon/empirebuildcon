"""Projects module: projects and their children (towers, configurations, specifications,
location advantages, construction updates, payment plans, amenities), plus the catalogue
(cities, localities, amenities) and the Google Maps pin resolver.

Layout (CODE_STYLE §4): `models.py` (tables), `schemas*.py` (request/response shapes),
`service.py` / `children.py` / `catalogue.py` (business rules), `routes*.py` (HTTP only),
`present.py` (rows → response shapes), `display.py` (₹ and area strings), `maps.py` and
`pluscode.py` (pin resolver), `blockers.py` (publish rules), `seed.py` (catalogue and samples).

Implements: ARCHITECTURE §4 (module), §6 (data model), §9 (events), §11 (permissions), §13 (maps);
D-002 (RERA), D-004/D-005 (no units or listings), D-014 (translations), D-015 (sample data).
"""

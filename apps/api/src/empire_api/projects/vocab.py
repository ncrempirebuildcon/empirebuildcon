"""The fixed word lists of the projects module (design contract enums), in one place.

Tables use them for CHECK constraints and the schemas use them as `Literal` types, so the
database, the API and the generated web client always agree on the allowed values.

DO NOT CHANGE a value without a migration: rows already store these strings, and the CHECK
constraints in migrations/versions/0002_catalogue.py list them.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

ProjectStatus = Literal["upcoming", "ongoing", "completed"]
SalesStatus = Literal["available", "sold_out", "off_market"]
PublishState = Literal["draft", "published", "archived"]
ProjectType = Literal["residential", "commercial", "mixed", "plots"]
AreaBasis = Literal["carpet", "builtup", "super_builtup", "plot"]
AreaUnit = Literal["sqft", "sqyd", "sqm"]
PinSource = Literal["url", "plus_code", "manual"]
TowerKind = Literal["tower", "phase", "block", "wing"]
TowerStatus = Literal["planned", "under_construction", "completed"]
PropertyType = Literal["apartment", "villa", "plot", "penthouse", "shop", "office", "other"]
AdvantageKind = Literal["transport", "school", "hospital", "shopping", "office", "leisure", "other"]
AmenityCategory = Literal[
    "lifestyle", "sports", "kids", "security", "green", "convenience", "other"
]

PROJECT_STATUSES: Final = get_args(ProjectStatus)
SALES_STATUSES: Final = get_args(SalesStatus)
PUBLISH_STATES: Final = get_args(PublishState)
PROJECT_TYPES: Final = get_args(ProjectType)
AREA_BASES: Final = get_args(AreaBasis)
AREA_UNITS: Final = get_args(AreaUnit)
PIN_SOURCES: Final = get_args(PinSource)
TOWER_KINDS: Final = get_args(TowerKind)
TOWER_STATUSES: Final = get_args(TowerStatus)
PROPERTY_TYPES: Final = get_args(PropertyType)
ADVANTAGE_KINDS: Final = get_args(AdvantageKind)
AMENITY_CATEGORIES: Final = get_args(AmenityCategory)

# WHY: D-002. Projects start in Uttar Pradesh under UP-RERA; another state only needs a new
# authority value on the project, not a code change.
DEFAULT_RERA_AUTHORITY: Final = "UP-RERA"
DEFAULT_STATE: Final = "Uttar Pradesh"


def check_in(column: str, values: tuple[str, ...]) -> str:
    """SQL for a CHECK constraint: `status IN ('a', 'b')`. Values are our own constants."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"

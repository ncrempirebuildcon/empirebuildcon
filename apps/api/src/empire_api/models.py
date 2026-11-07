"""Import every model module so `Base.metadata` knows all tables (Alembic, tests).

When you add a module with tables, import it here; tests/test_migrations.py then fails until a
migration creates the new tables.
"""

from __future__ import annotations

from empire_api.ai import models as ai_models
from empire_api.content import models as content_models
from empire_api.db import Base
from empire_api.leads import models as lead_models
from empire_api.mail import models as mail_models
from empire_api.media import models as media_models
from empire_api.platform import models as platform_models
from empire_api.projects import models as project_models
from empire_api.seo import models as seo_models
from empire_api.site_settings import models as settings_models
from empire_api.users import models as user_models

# Tables created by migrations only, with no ORM model: `knowledge_chunk` exists only where
# pgvector is installed (migration 0008, D-059) and is used through SQL (ai/store.py).
SQL_ONLY_TABLES = frozenset({"knowledge_chunk"})


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Alembic comparison filter: leave the SQL-only tables (and their indexes) alone."""
    table = getattr(obj, "table", None)
    table_name = name if type_ == "table" else getattr(table, "name", None)
    return table_name not in SQL_ONLY_TABLES


__all__ = [
    "SQL_ONLY_TABLES",
    "Base",
    "ai_models",
    "content_models",
    "include_object",
    "lead_models",
    "mail_models",
    "media_models",
    "platform_models",
    "project_models",
    "seo_models",
    "settings_models",
    "user_models",
]

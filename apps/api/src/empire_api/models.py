"""Import every model module so `Base.metadata` knows all tables (Alembic, tests).

When you add a module with tables, import it here; tests/test_migrations.py then fails until a
migration creates the new tables.
"""

from __future__ import annotations

from empire_api.db import Base
from empire_api.media import models as media_models
from empire_api.platform import models as platform_models
from empire_api.projects import models as project_models
from empire_api.site_settings import models as settings_models
from empire_api.users import models as user_models

__all__ = [
    "Base",
    "media_models",
    "platform_models",
    "project_models",
    "settings_models",
    "user_models",
]

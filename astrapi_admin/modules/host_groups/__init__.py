from pathlib import Path

from astrapi_core.system.db import register_table
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

_DDL = """
    CREATE TABLE IF NOT EXISTS host_groups (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL DEFAULT '',
        description TEXT    NOT NULL DEFAULT '',
        policy_ids  TEXT    NOT NULL DEFAULT '',
        enabled     INTEGER NOT NULL DEFAULT 1
    )"""

register_table(_KEY, _DDL, list_fields=["policy_ids"])

from astrapi_core.ui.controls import Col, ContentTable  # noqa: E402
from astrapi_core.ui.field_resolver import register_options_fetcher as _reg  # noqa: E402

from astrapi_admin.modules.host_groups.ui.crud import api_router as router  # noqa: E402
from astrapi_admin.modules.host_groups.ui.crud import groups_for_select  # noqa: E402
from astrapi_admin.modules.host_groups.ui.crud import router as ui_router  # noqa: E402


def _groups_options_fetcher(endpoint: str) -> list:
    return groups_for_select()


# Ohne diese Registrierung bleibt hosts.group_ids (options_endpoint:
# /api/host_groups/for-select) dauerhaft leer -- siehe gleiche
# Begruendung in modules/policies/__init__.py, T-270-ADMIN.
_reg("/api/host_groups/for-select", _groups_options_fetcher)

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_content=ContentTable(
        has_run_buttons=False,
        columns=[
            Col.trunc("description", "Beschreibung"),
            Col.join("policy_ids", "Policies"),
        ],
    ),
)

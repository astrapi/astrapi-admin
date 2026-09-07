from pathlib import Path

from astrapi_core.ui.controls import Header
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

from astrapi_core.ui.field_resolver import register_options_fetcher as _reg  # noqa: E402

from astrapi_admin.modules.user_policies.engine import user_policies_for_select  # noqa: E402
from astrapi_admin.modules.user_policies.ui import api_router, user_policies_table  # noqa: E402
from astrapi_admin.modules.user_policies.ui import router as ui_router  # noqa: E402


def _user_policies_options_fetcher(endpoint: str) -> list:
    return user_policies_for_select()


# Ohne diese Registrierung bleibt hosts.user_policy_ids (options_endpoint:
# /api/user_policies/for-select) dauerhaft leer -- gleiche Begruendung wie
# bei modules/policies/__init__.py, T-270-ADMIN.
_reg("/api/user_policies/for-select", _user_policies_options_fetcher)

module = load_modul(
    Path(__file__).parent,
    _KEY,
    api_router,
    ui_router,
    ui_header=Header(
        [
            Header.action_button(
                "Importieren",
                hx_get=f"/ui/{_KEY}/import",
                hx_target="body",
                style="ghost",
                icon="arrow-up",
            ),
            Header.action_button(
                "Neue Nutzer-Policy",
                hx_get=f"/ui/{_KEY}/new",
                hx_target="body",
                style="primary",
                icon="plus",
            ),
        ]
    ),
    ui_content=user_policies_table,
)

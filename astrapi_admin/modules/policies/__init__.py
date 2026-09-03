from pathlib import Path

from astrapi_core.ui.controls import Header
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

from astrapi_core.ui.field_resolver import register_options_fetcher as _reg  # noqa: E402

from astrapi_admin.modules.policies.engine import policies_for_select  # noqa: E402
from astrapi_admin.modules.policies.ui import api_router, policies_table  # noqa: E402
from astrapi_admin.modules.policies.ui import router as ui_router  # noqa: E402


def _policies_options_fetcher(endpoint: str) -> list:
    # hosts/config/schema.yaml haengt ?context=host an -- blendet dort
    # 'nur ueber Gruppen zuweisbar' markierte Policies aus der Direkt-
    # Zuweisung aus (host_groups/config/schema.yaml haengt nichts an,
    # bleibt ungefiltert, siehe engine.py::policies_for_select()).
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(endpoint).query)
    is_host_context = query.get("context", [""])[0] == "host"
    return policies_for_select(exclude_group_only=is_host_context)


# Ohne diese Registrierung bleibt jedes options_endpoint-Multiselect-Feld,
# das auf /api/policies/for-select zeigt (hosts.policy_ids,
# host_groups.policy_ids), dauerhaft leer -- resolve_options_endpoint()
# faellt bei unbekanntem Praefix still auf [] zurueck, kein Fehler sichtbar
# (T-270-ADMIN: "Policy laesst sich keinem Host zuweisen").
_reg("/api/policies/for-select", _policies_options_fetcher)

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
                "Neue Policy",
                hx_get=f"/ui/{_KEY}/new",
                hx_target="body",
                style="primary",
                icon="plus",
            ),
        ]
    ),
    ui_content=policies_table,
)

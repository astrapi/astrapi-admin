from pathlib import Path

from astrapi_core.system.db import register_table
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

_DDL = """
    CREATE TABLE IF NOT EXISTS hosts (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        hostname           TEXT    NOT NULL DEFAULT '',
        label              TEXT    NOT NULL DEFAULT '',
        os_type            TEXT    NOT NULL DEFAULT '',
        group_ids          TEXT    NOT NULL DEFAULT '',
        policy_ids         TEXT    NOT NULL DEFAULT '',
        mirror_repos       TEXT    NOT NULL DEFAULT '',
        token_hash         TEXT    NOT NULL DEFAULT '',
        last_seen          TEXT    NOT NULL DEFAULT '',
        last_report        TEXT    NOT NULL DEFAULT '',
        last_status        TEXT    NOT NULL DEFAULT '',
        pending_action     TEXT    NOT NULL DEFAULT '',
        updates_available  INTEGER NOT NULL DEFAULT -1,
        security_updates_available INTEGER NOT NULL DEFAULT -1,
        updates_package_list TEXT NOT NULL DEFAULT '',
        security_updates_package_list TEXT NOT NULL DEFAULT '',
        updates_checked_at TEXT    NOT NULL DEFAULT '',
        proxmox_vmid       INTEGER NOT NULL DEFAULT -1,
        snapshot_before_update INTEGER NOT NULL DEFAULT 1,
        enabled            INTEGER NOT NULL DEFAULT 1
    )"""

register_table(
    _KEY,
    _DDL,
    list_fields=[
        "group_ids", "policy_ids", "mirror_repos",
        "updates_package_list", "security_updates_package_list",
    ],
)

from astrapi_core.modules.notify.engine import register_source  # noqa: E402
from astrapi_core.ui.controls import Col, ContentTable, Header  # noqa: E402
from astrapi_core.ui.field_resolver import register_options_fetcher as _reg  # noqa: E402

# Fuer die Quellen-Filterung in der Notify-Job-Konfiguration (E-008) --
# ohne Registrierung waere "hosts" dort nicht als Option waehlbar, siehe
# astrapi_core.modules.notify.engine-Docstring.
register_source(_KEY, "Hosts")

from astrapi_admin.modules.hosts import mirror_client  # noqa: E402
from astrapi_admin.modules.hosts.ui import pairing as _pairing  # noqa: E402,F401 – registriert Routen auf ui_router
from astrapi_admin.modules.hosts.ui import updates as _updates  # noqa: E402,F401 – registriert Routen auf ui_router
from astrapi_admin.modules.hosts.ui.crud import api_router as router  # noqa: E402
from astrapi_admin.modules.hosts.ui.crud import router as ui_router  # noqa: E402


def _mirror_repos_options_fetcher(endpoint: str) -> list:
    return mirror_client.list_debian_repos()


# Ohne diese Registrierung bleibt das Mirror-Quellen-Multiselect im
# Host-Dialog dauerhaft leer -- gleiche Fehlerklasse wie T-270-ADMIN.
_reg("/api/hosts/mirror-repos-for-select", _mirror_repos_options_fetcher)

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header([
        Header.action_button(
            "Host koppeln",
            hx_get=f"/ui/{_KEY}/pair",
            hx_target="body",
            style="primary",
            icon="plus",
        ),
    ]),
    ui_content=ContentTable(
        has_run_buttons=False,
        # has_status=False: sonst haengt list_wrapper_inner.html eine
        # zweite, generische Status-Spalte an (dasselbe last_status-Feld,
        # aber ohne die eigene OK/Drift/Fehler/Konflikt-Unterscheidung
        # unten) -- Duplikat, T-285-ADMIN.
        has_status=False,
        columns=[
            Col.badge_enum("os_type", "OS", {
                "archlinux": {"label": "Arch", "cls": "badge-status-ok"},
                "debian":    {"label": "Debian", "cls": "badge-status-warn"},
            }),
            Col.badge_enum("last_status", "Status", {
                "ok":       {"label": "OK", "cls": "badge-status-ok"},
                "drift":    {"label": "Drift", "cls": "badge-status-warn"},
                "error":    {"label": "Fehler", "cls": "badge-status-err"},
                "conflict": {"label": "Konflikt", "cls": "badge-status-warn"},
            }),
            Col.text("updates_available", "Updates", sortable=False),
            Col.text("proxmox_vmid", "Proxmox", sortable=False),
            Col.text("last_seen", "Zuletzt gesehen"),
        ],
    ),
)

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
        reboot_required    INTEGER NOT NULL DEFAULT 0,
        user_policy_ids    TEXT    NOT NULL DEFAULT '',
        user_inventory     TEXT    NOT NULL DEFAULT '',
        user_inventory_checked_at TEXT NOT NULL DEFAULT '',
        enabled            INTEGER NOT NULL DEFAULT 1
    )"""

register_table(
    _KEY,
    _DDL,
    list_fields=[
        "group_ids", "policy_ids", "mirror_repos",
        "updates_package_list", "security_updates_package_list",
        "user_policy_ids",
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
from astrapi_admin.modules.hosts.ui import user_inventory as _user_inventory  # noqa: E402,F401 – registriert Routen auf ui_router
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
        # Die generische Status-Spalte wird jetzt bewusst genutzt (T-305-
        # ADMIN-Nachfolger, Nutzerentscheidung 2026-09-04) -- drift/conflict
        # werden dafuer in hosts/ui/crud.py::_resolve_labels() auf
        # "warning" abgebildet (generisches status_inline() kennt nur ok/
        # error/warning/running/pending/neu). Die verlorene Drift-vs-
        # Konflikt-Unterscheidung ist ueber den bereits vorhandenen "Log
        # anzeigen"-Button (card_actions, type: log) weiterhin einen
        # Klick entfernt einsehbar -- jeder Report haengt schon die genaue
        # summarize()-Zusammenfassung ins Activity-Log (api/agent.py::
        # post_report()), nicht erst seit dieser Aenderung.
        columns=[
            Col.text("os_type", "OS", css="col-info", sortable=False),
            Col.dot_text("updates_available", "Updates", category_key="updates_category", css="col-info"),
            Col.text("proxmox_vmid", "Proxmox", css="col-info", sortable=False),
            # "Letzter Lauf" statt "Zuletzt gesehen": last_seen wird
            # ausschliesslich in api/auth.py::require_host() gesetzt, bei
            # jedem authentifizierten Agent-Call (GET /policy, POST
            # /report -- beide nur als Teil eines apply()-Laufs, in
            # dieser Reihenfolge). Der zuletzt geschriebene Wert
            # entspricht damit dem Abschluss des letzten Laufs.
            Col.text("last_seen", "Letzter Lauf", css="col-date"),
            # next_run_display kommt aus dem Agenten selbst (systemd
            # list-timers, inkl. Jitter) statt einer server-seitigen
            # last_seen+Intervall-Schaetzung -- siehe hosts/ui/crud.py::
            # _next_run_at(). Braucht Agent >= v26.9.2, aeltere Agenten
            # liefern "unbekannt".
            Col.text("next_run_display", "Nächster Lauf", css="col-date", sortable=False),
        ],
    ),
)

# astrapi_admin/modules/hosts/ui/crud.py
import json
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import resolve_options_endpoint
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.render import render
from astrapi_core.ui.store import SqliteTableStore
from fastapi import Request
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.hosts import mirror_client
from astrapi_admin.modules.hosts import mirror_repos as mirror_repos_mod
from astrapi_admin.modules.policies.engine import group_policy_ids
from astrapi_admin.modules.user_policies.engine import group_user_policy_ids

KEY = "hosts"
_DIR = Path(__file__).parent.parent
store = SqliteTableStore(KEY)


def _resolve_fields(fields: list, item: dict | None = None) -> list:
    """Aufloesen der options_endpoint-Felder wie ueberall -- zusaetzlich
    werden fuer policy_ids/mirror_repos ueber eine Gruppe geerbte Werte als
    'locked' markiert (field_renderer.html in astrapi-core: angehakt, aber
    nicht abwaehlbar -- sonst wirkt es, als koennte man sie am Host
    entfernen, sie kaemen aber ueber die Gruppe ohnehin wieder)."""
    resolved = resolve_options_endpoint(fields)
    if not item:
        return resolved

    locked_by_field = {
        "mirror_repos": mirror_repos_mod.group_mirror_repos(item),
        "policy_ids": group_policy_ids(item),
        "user_policy_ids": group_user_policy_ids(item),
    }
    for f in resolved:
        locked = locked_by_field.get(f.get("name"))
        if not locked:
            continue
        for opt in f.get("options") or []:
            if opt["value"] in locked:
                opt["locked"] = True

    # snapshot_before_update ist nur bei einem erkannten Proxmox-LXC
    # ueberhaupt wirksam (siehe hosts/ui/updates.py -- der Trigger prueft
    # zusaetzlich proxmox_vmid >= 0). Ohne Proxmox-Zuordnung blenden wir
    # das Feld ganz aus, statt einen wirkungslosen Schalter zu zeigen.
    # Nutzerwunsch (2026-09-02): "wenn ich einen LXC habe der kein
    # Proxmox-LXC ist, kann das Toggle Snapshot entfallen".
    #
    # Bewusst KEIN Filtern von schema["fields"] selbst (crud_blueprint.py
    # liest das beim Speichern separat, unabhaengig von dieser Funktion)
    # -- das Feld bleibt beim Speichern also weiterhin Teil der Form-
    # Verarbeitung und wird dabei stumpf auf False geschrieben (fehlender
    # Toggle heisst "aus"). Das ist hier folgenlos: der einzige Lesezugriff
    # auf snapshot_before_update prueft IMMER zusaetzlich proxmox_vmid >= 0,
    # der gespeicherte Wert wird fuer diese Hosts also nie ausgewertet.
    if (item.get("proxmox_vmid") if item.get("proxmox_vmid") is not None else -1) < 0:
        resolved = [f for f in resolved if f.get("name") != "snapshot_before_update"]

    return resolved


def _resolve_labels(item_id: str, item: dict) -> dict:
    """Loest group_ids/policy_ids fuer die Listen-/Bearbeiten-ANZEIGE gegen
    Name/Beschreibung auf (analog zu astrapi-syncs devices._resolve_folder_labels,
    T-225-SYNC) -- vermeidet rohe IDs in der Oberflaeche.

    'description' fuellt die generische NAME-Spalte der Listenansicht
    (list_wrapper_inner.html: item_data.description or .job or .host or
    item_name) -- ohne das zeigte sie die rohe DB-ID statt des Hostnamens.
    Kein separates 'Anzeigename'-Feld mehr (T-285-ADMIN, Nutzerwunsch:
    "der Hostname reicht mir")."""
    item["description"] = item.get("hostname") or item_id

    from astrapi_admin.modules.host_groups.ui.crud import groups_for_select

    group_labels = {opt["value"]: opt["label"] for opt in groups_for_select()}
    item["group_ids"] = [group_labels.get(gid, gid) for gid in (item.get("group_ids") or [])]

    from astrapi_admin.modules.policies.engine import policies_for_select

    policy_labels = {opt["value"]: opt["label"] for opt in policies_for_select()}
    item["policy_ids"] = [policy_labels.get(pid, pid) for pid in (item.get("policy_ids") or [])]

    item["updates_category"] = _updates_category(
        item.get("updates_available"), item.get("security_updates_available")
    )
    item["updates_available"] = _format_updates_available(
        item.get("updates_available"),
        item.get("security_updates_available"),
        item.get("pending_action"),
    )
    item["proxmox_vmid"] = _format_proxmox_vmid(item.get("proxmox_vmid"))
    item["last_status"] = _display_status(item.get("last_status"))
    item["os_type"] = _format_os_type(item.get("os_type"))
    item["next_run_display"] = _next_run_at(item.get("last_report"))

    return item


def _format_proxmox_vmid(value) -> str:
    if value is None or value < 0:
        return "kein Proxmox-LXC"
    return f"VMID {value}"


def _display_status(value: str | None) -> str | None:
    """Nutzerentscheidung 2026-09-04: die generische Status-Spalte
    (status_inline() in astrapi-core, kennt nur ok/error/warning/running/
    pending/neu) wird jetzt genutzt statt einer eigenen badge_enum-Spalte
    -- 'drift' und 'conflict' (siehe api/agent.py::_REPORT_STATUSES)
    werden dafuer beide als 'warning' angezeigt. Der gespeicherte Rohwert
    bleibt unveraendert (nur die ANZEIGE wird hier umgeschrieben) -- die
    genaue Unterscheidung ist weiterhin ueber "Log anzeigen" einsehbar,
    jeder Report haengt schon summarize()s Zusammenfassung ins
    Activity-Log."""
    return "warning" if value in ("drift", "conflict") else value


def _format_updates_available(value, security_value=None, pending_action=None) -> str:
    """security_value ist nur bei Debian-Hosts gesetzt (>= 0, siehe E-008)
    -- bei Arch (immer -1, checkupdates kennt keine Security-Kategorie)
    bleibt es unerwaehnt statt "0 sicherheitsrelevant" vorzutaeuschen.

    pending_action zeigt an, ob ein Admin "Update anstoßen" bereits
    geklickt hat (hosts/ui/updates.py) -- ohne diesen Hinweis war in der
    Liste nicht erkennbar, ob eine Freigabe schon erfolgt ist oder noch
    aussteht, bis der Agent beim naechsten Poll berichtet."""
    if value is None or value < 0:
        base = "noch nicht geprüft"
    elif value == 0:
        base = "aktuell"
    else:
        base = f"{value} Update{'s' if value != 1 else ''}"
        if security_value is not None and security_value > 0:
            base += f" ({security_value} sicherheitsrelevant)"

    if pending_action == "update":
        base += " -- angefordert, wartet auf Agent"

    return base


def _updates_category(value, security_value=None) -> str:
    """Farbpunkt-Kategorie fuer Col.dot_text (Nutzerwunsch 2026-09-04):
    gruen = keine Updates, orange = normale Updates, rot =
    sicherheitsrelevante Updates dabei. Kein Punkt (leerer String), wenn
    der Stand unbekannt ist (noch nie geprueft) -- ein gruener Punkt
    waere dort falsch beruhigend."""
    if value is None or value < 0:
        return ""
    if value == 0:
        return "ok"
    if security_value is not None and security_value > 0:
        return "error"
    return "warning"


def _format_os_type(value: str | None) -> str:
    return {"archlinux": "Arch", "debian": "Debian"}.get(value or "", value or "—")


def _next_run_at(last_report_json: str | None) -> str:
    """Liest next_run_at aus dem zuletzt gespeicherten Report (last_report
    ist bereits ein JSON-Blob mit status/summary/details, siehe
    api/agent.py::post_report()) -- bewusst KEINE eigene DB-Spalte dafuer:
    das Feld haengt ohnehin schon im details-Dict mit durch, eine neue
    Spalte haette nur Migrationsrisiko fuer bereits existierende
    Host-Zeilen gebracht (siehe T-308-CORE, save_item()/create_item()
    in astrapi-core bauen INSERT/UPDATE nur aus den uebergebenen Keys --
    ohne Migration wuerde das an einer bestehenden DB mit "no such
    column" scheitern). Aeltere Agenten (vor v26.9.2) kennen das Feld
    noch nicht -- liefert dann "unbekannt", nicht faelschlich leer."""
    if not last_report_json:
        return "unbekannt"
    try:
        details = json.loads(last_report_json).get("details") or {}
    except (ValueError, TypeError):
        return "unbekannt"
    return details.get("next_run_at") or "unbekannt"


api_router = make_htmx_crud_router(
    KEY,
    _DIR / "config" / "schema.yaml",
)


def hosts_for_select() -> list[dict]:
    return [
        {"value": hid, "label": h.get("label") or h.get("hostname") or hid}
        for hid, h in store.list().items()
    ]


@api_router.get("/for-select")
def for_select():
    return {"options": hosts_for_select()}


@api_router.get("/mirror-repos-for-select")
def mirror_repos_for_select():
    return {"options": mirror_client.list_debian_repos()}


@api_router.get("/{item_id}/logs", response_class=HTMLResponse)
def get_logs(item_id: str, request: Request):
    """Log-Modal (astrapi-core: type: log card_action) -- ein 'Run' ist
    hier kein langer Job wie bei borg/rsync, sondern ein einzelner
    Policy-Report. post_report() haengt bei einem echten Update-Versuch
    zusaetzliche Zeilen (Paketliste + Roh-Ausgabe) an denselben Log-Eintrag
    an, siehe api/agent.py."""
    from astrapi_core.system.activity_log import get_log_lines, list_runs_for_item

    runs = list_runs_for_item(KEY, item_id)
    act_log_id = runs[0]["id"] if runs else None
    lines = [r["line"] for r in get_log_lines(act_log_id)] if act_log_id else []
    dates = [{"id": str(r["id"]), "label": r["started_at"] or str(r["id"])} for r in runs]
    selected = str(act_log_id) if act_log_id else None

    host = store.get(item_id)
    description = (host.get("label") or host.get("hostname") or item_id) if host else item_id

    return render(request, "dialog_log.html", {
        "module": KEY,
        "item_id": item_id,
        "description": description,
        "dates": dates,
        "selected": selected,
        "lines": lines,
        "live": False,
    })


@api_router.get("/{item_id}/logs/{log_id}", response_class=HTMLResponse)
def get_log_by_id(item_id: str, log_id: str, request: Request):
    from astrapi_core.system.activity_log import get_log_lines

    lines = [r["line"] for r in get_log_lines(int(log_id))] if log_id.isdigit() else []
    return render(request, "partials/dialogs/log_content.html", {"lines": lines, "date": log_id})


router = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Host",
    description_field="hostname",
    has_run_buttons=False,
    has_toggle=True,
    resolve_fields_fn=_resolve_fields,
    list_item_transform=_resolve_labels,
)

# astrapi_admin/modules/hosts/ui/crud.py
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
    }
    for f in resolved:
        locked = locked_by_field.get(f.get("name"))
        if not locked:
            continue
        for opt in f.get("options") or []:
            if opt["value"] in locked:
                opt["locked"] = True
    return resolved


def _resolve_labels(item_id: str, item: dict) -> dict:
    """Loest group_ids/policy_ids fuer die Listen-/Bearbeiten-ANZEIGE gegen
    Name/Beschreibung auf (analog zu astrapi-syncs devices._resolve_folder_labels,
    T-225-SYNC) -- vermeidet rohe IDs in der Oberflaeche."""
    from astrapi_admin.modules.host_groups.ui.crud import groups_for_select

    group_labels = {opt["value"]: opt["label"] for opt in groups_for_select()}
    item["group_ids"] = [group_labels.get(gid, gid) for gid in (item.get("group_ids") or [])]

    from astrapi_admin.modules.policies.engine import policies_for_select

    policy_labels = {opt["value"]: opt["label"] for opt in policies_for_select()}
    item["policy_ids"] = [policy_labels.get(pid, pid) for pid in (item.get("policy_ids") or [])]

    item["updates_available"] = _format_updates_available(
        item.get("updates_available"), item.get("security_updates_available")
    )
    item["proxmox_vmid"] = _format_proxmox_vmid(item.get("proxmox_vmid"))

    return item


def _format_proxmox_vmid(value) -> str:
    if value is None or value < 0:
        return "kein Proxmox-LXC"
    return f"VMID {value}"


def _format_updates_available(value, security_value=None) -> str:
    """security_value ist nur bei Debian-Hosts gesetzt (>= 0, siehe E-008)
    -- bei Arch (immer -1, checkupdates kennt keine Security-Kategorie)
    bleibt es unerwaehnt statt "0 sicherheitsrelevant" vorzutaeuschen."""
    if value is None or value < 0:
        return "noch nicht geprüft"
    if value == 0:
        return "aktuell"
    base = f"{value} Update{'s' if value != 1 else ''}"
    if security_value is not None and security_value > 0:
        base += f" ({security_value} sicherheitsrelevant)"
    return base


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

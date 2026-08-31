# astrapi_admin/modules/hosts/ui/crud.py
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import resolve_options_endpoint
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.store import SqliteTableStore

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

    return item


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

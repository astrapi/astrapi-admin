# astrapi_admin/modules/host_groups/ui/crud.py
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import resolve_options_endpoint
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.store import SqliteTableStore

KEY = "host_groups"
_DIR = Path(__file__).parent.parent
store = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


def _resolve_labels(item_id: str, item: dict) -> dict:
    """list_wrapper_inner.html rendert die NAME-Spalte immer fest aus
    item_data.description (oder .job/.host/item_name) -- host_groups hat
    wie policies ein eigenes 'name'-Feld (Pflicht beim Anlegen) UND ein
    separates, optionales 'description'-Feld. Ohne Aufloesung kollidieren
    beide auf demselben Dict-Key (siehe [[T-285-ADMIN]]/[[T-288-ADMIN]] --
    dieselbe Fehlerklasse, hier zum dritten Mal). 'description_text' ist
    der neue, kollisionsfreie Schluessel fuer die echte Beschreibung-
    Spalte, 'description' traegt jetzt den Namen fuers NAME-Feld.

    Zusaetzlich: die POLICIES-Spalte (Col.join('policy_ids', ...)) verbindet
    bislang nur die rohen Policy-IDs, keine Namensaufloesung -- 'policy_names'
    liefert die lesbaren Namen dafuer."""
    from astrapi_admin.modules.policies import engine as policies_engine

    names = {pid: p.get("name") or pid for pid, p in policies_engine.list_policies().items()}
    return {
        **item,
        "description": item.get("name") or item_id,
        "description_text": item.get("description") or "—",
        "policy_names": [names.get(pid, pid) for pid in (item.get("policy_ids") or [])],
    }


def groups_for_select() -> list[dict]:
    return [
        {"value": gid, "label": g.get("name") or gid}
        for gid, g in store.list().items()
    ]


api_router = make_htmx_crud_router(
    KEY,
    _DIR / "config" / "schema.yaml",
)


@api_router.get("/for-select")
def for_select():
    return {"options": groups_for_select()}


router = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Gruppe",
    description_field="name",
    has_run_buttons=False,
    has_toggle=False,
    resolve_fields_fn=_resolve_fields,
    list_item_transform=_resolve_labels,
)

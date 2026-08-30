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
)

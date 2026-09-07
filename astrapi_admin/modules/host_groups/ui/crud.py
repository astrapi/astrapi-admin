# astrapi_admin/modules/host_groups/ui/crud.py
import json
import re

from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import resolve_options_endpoint
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.render import render
from astrapi_core.ui.schema_loader import load_schema
from astrapi_core.ui.store import SqliteTableStore
from fastapi import Request, Response
from fastapi.responses import HTMLResponse

KEY = "host_groups"
_DIR = Path(__file__).parent.parent
_SCHEMA_PATH = str(_DIR / "config" / "schema.yaml")
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
    liefert die lesbaren Namen dafuer. 'user_policy_names' macht dasselbe
    fuer die neue user_policy_ids-Gruppenzuweisung (astrapi-hub-Vault
    E-013-Folge)."""
    from astrapi_admin.modules.policies import engine as policies_engine
    from astrapi_admin.modules.user_policies import engine as user_policies_engine

    names = {pid: p.get("name") or pid for pid, p in policies_engine.list_policies().items()}
    user_names = {pid: p.get("name") or pid for pid, p in user_policies_engine.list_user_policies().items()}
    return {
        **item,
        "description": item.get("name") or item_id,
        "description_text": item.get("description") or "—",
        "policy_names": [names.get(pid, pid) for pid in (item.get("policy_ids") or [])],
        "user_policy_names": [
            user_names.get(pid, pid) for pid in (item.get("user_policy_ids") or [])
        ],
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


# ── Export/Import (analog zu policies/ui.py, hier fuer den generischen
# schema-getriebenen crud_blueprint-Router nachgebaut -- der hat dafuer
# keine eingebaute Unterstuetzung, siehe dessen Docstring "Modulspezifische
# Extrarouten einfach hinzufuegen") ─────────────────────────────────────


def _slug(text: str) -> str:
    """Dateiname-tauglicher Kurzname fuer den Export-Download, analog zu
    policies/ui.py::_slug()."""
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", (text or "").strip().lower()).strip("-")
    return text or "gruppe"


@router.get(f"/ui/{KEY}/{{item_id}}/export")
def host_groups_export(item_id: str):
    """Reiner Download-Link -- liefert das rohe, gespeicherte Gruppen-JSON
    (inkl. policy_ids/user_policy_ids/mirror_repos als rohe IDs -- diese
    ergeben nur Sinn, wenn dieselben IDs auf dem Zielserver existieren;
    andernfalls erscheinen sie im Import-Formular schlicht unausgewählt,
    kein Fehler). Analog zu policies/ui.py::policies_export()."""
    item = store.get(item_id)
    if item is None:
        return Response(status_code=404)
    filename = f"host-group-{_slug(item.get('name') or item_id)}.json"
    return Response(
        content=json.dumps(item, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(f"/ui/{KEY}/import", response_class=HTMLResponse)
def host_groups_import_modal(request: Request):
    return render(request, f"{KEY}/dialogs/import/modal.html", dict(error=None, raw=None))


@router.post(f"/ui/{KEY}/import-preview", response_class=HTMLResponse)
async def host_groups_import_preview(request: Request):
    """Legt NICHTS an -- parst nur das eingefügte JSON und rendert denselben
    generischen create_edit_modal.html-Dialog wie 'Neu', nur mit
    vorbefüllten Werten (item_id=None -> Absenden läuft über den normalen
    create_apply()-Pfad aus crud_blueprint.py). Analog zu
    policies/ui.py::policies_import_preview()."""
    form = await request.form()
    raw = (form.get("import_json") or "").strip()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return render(
            request,
            f"{KEY}/dialogs/import/modal.html",
            dict(error="Kein gültiges JSON.", raw=raw),
            status_code=422,
        )
    if not isinstance(data, dict) or not (data.get("name") or "").strip():
        return render(
            request,
            f"{KEY}/dialogs/import/modal.html",
            dict(error="JSON enthält kein (nicht-leeres) 'name'-Feld.", raw=raw),
            status_code=422,
        )

    def _as_list(value) -> list:
        return value if isinstance(value, list) else []

    schema = load_schema(_SCHEMA_PATH)
    item = {
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "policy_ids": _as_list(data.get("policy_ids")),
        "user_policy_ids": _as_list(data.get("user_policy_ids")),
        "mirror_repos": _as_list(data.get("mirror_repos")),
        "enabled": bool(data.get("enabled", True)),
    }
    return render(
        request,
        "partials/create_edit/create_edit_modal.html",
        dict(
            schema=_resolve_fields(schema["fields"]),
            id_field=schema["id_field"],
            modal_width=schema["modal_width"],
            item=item,
            item_id=None,
            submit_url=f"/ui/{KEY}/",
            method="post",
            title="Gruppe importieren",
            reload_url=f"/ui/{KEY}/content",
            container_id=f"mod-{KEY}",
            loading_id=f"{KEY}-loading",
        ),
    )

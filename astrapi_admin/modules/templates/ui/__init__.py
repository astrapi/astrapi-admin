# astrapi_admin/modules/templates/ui/__init__.py
"""FastAPI-Router fuer den Vorlagen-Editor -- eigener, strukturierter
Dialog statt generischem crud_blueprint, analog zu policies/ui/__init__.py
(Pakete/Config-Dateien/Services/Parameter brauchen jeweils eigene
Tabellen-/Listen-Widgets, kein simples Formularfeld-Set)."""
import uuid

from astrapi_core.ui.controls import Col, ContentTable
from astrapi_core.ui.page_factory import register_content_renderer
from astrapi_core.ui.render import render, render_string
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.templates import engine

KEY = "templates"
_C_ID = f"mod-{KEY}"
_L_ID = f"{KEY}-loading"

router = APIRouter()
api_router = APIRouter()

templates_table = ContentTable(
    has_create=False,
    has_run_buttons=False,
    has_toggle=True,
    columns=[
        Col.trunc("description", "Beschreibung"),
        Col.text("summary", "Umfang", sortable=False),
    ],
)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _summary(t: dict) -> str:
    n_pkg = len((t.get("packages_arch") or {}).get("present") or []) + len(
        (t.get("packages_debian") or {}).get("present") or []
    )
    parts = []
    if n_pkg:
        parts.append(f"{n_pkg} Pakete")
    if t.get("config_files"):
        parts.append(f"{len(t['config_files'])} Configs")
    if t.get("params"):
        parts.append(f"{len(t['params'])} Parameter")
    return ", ".join(parts) or "leer"


def _list_ctx() -> dict:
    tpls = engine.list_templates()
    return {
        "module": KEY,
        "cfg": {tid: {**t, "summary": _summary(t)} for tid, t in tpls.items()},
        "container_id": _C_ID,
        "loading_id": _L_ID,
    }


def _render_content(request):
    return render_string(request, "content.html", _list_ctx())


register_content_renderer(KEY, _render_content)


# ── Liste ────────────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def templates_content(request: Request):
    return render(request, "content.html", _list_ctx())


# ── Dialoge ──────────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/new", response_class=HTMLResponse)
def templates_new(request: Request):
    return render(request, f"{KEY}/dialogs/edit/modal.html", dict(tpl=None, error=None))


@router.get(f"/ui/{KEY}/{{template_id}}/edit", response_class=HTMLResponse)
def templates_edit(template_id: str, request: Request):
    tpl = engine.get_template(template_id)
    if tpl is None:
        return HTMLResponse("", status_code=404)
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(tpl={**tpl, "id": template_id}, error=None),
    )


@router.get(f"/ui/{KEY}/{{template_id}}/delete", response_class=HTMLResponse)
def templates_delete_modal(template_id: str, request: Request):
    tpl = engine.get_template(template_id)
    return render(
        request,
        "dialog_confirm.html",
        dict(
            title="Löschen",
            description=tpl.get("name", template_id) if tpl else template_id,
            verb="löschen",
            confirm_url=f"/api/{KEY}/{template_id}",
            method="delete",
            reload_url=f"/ui/{KEY}/content",
        ),
    )


@router.get(f"/ui/{KEY}/{{template_id}}/toggle", response_class=HTMLResponse)
def templates_toggle_modal(template_id: str, request: Request):
    tpl = engine.get_template(template_id) or {}
    enabled = request.query_params.get("enabled", "True")
    verb = "deaktivieren" if enabled == "True" else "aktivieren"
    return render(
        request,
        "dialog_confirm.html",
        dict(
            description=tpl.get("name", template_id),
            verb=verb,
            confirm_url=f"/api/{KEY}/{template_id}/toggle",
            method="patch",
            reload_url=f"/ui/{KEY}/content",
        ),
    )


# ── Form-Parsing ─────────────────────────────────────────────────────────


async def _parse_form(request: Request) -> dict:
    form = await request.form()

    paths = form.getlist("cf_path")
    actions = form.getlist("cf_action")
    contents = form.getlist("cf_content")
    modes = form.getlist("cf_mode")
    owners = form.getlist("cf_owner")
    groups = form.getlist("cf_group")
    forces = form.getlist("cf_force")
    config_files = []
    for i, path in enumerate(paths):
        path = path.strip()
        if not path:
            continue
        config_files.append(
            {
                "path": path,
                "action": actions[i] if i < len(actions) else "enforce",
                "content": contents[i] if i < len(contents) else "",
                "mode": (modes[i] if i < len(modes) else "").strip() or "0644",
                "owner": (owners[i] if i < len(owners) else "").strip() or "root",
                "group": (groups[i] if i < len(groups) else "").strip() or "root",
                "force": (forces[i] if i < len(forces) else "0") == "1",
            }
        )

    svc_names = form.getlist("svc_name")
    svc_states = form.getlist("svc_state")
    services = []
    for i, name in enumerate(svc_names):
        name = name.strip()
        if not name:
            continue
        services.append(
            {"name": name, "state": svc_states[i] if i < len(svc_states) else "enabled_started"}
        )

    param_keys = form.getlist("param_key")
    param_labels = form.getlist("param_label")
    param_defaults = form.getlist("param_default")
    param_requireds = form.getlist("param_required")
    params = []
    for i, key in enumerate(param_keys):
        key = key.strip()
        if not key:
            continue
        default = (param_defaults[i] if i < len(param_defaults) else "").strip()
        params.append(
            {
                "key": key,
                "label": (param_labels[i] if i < len(param_labels) else "").strip() or key,
                "default": default or None,
                "required": (param_requireds[i] if i < len(param_requireds) else "0") == "1",
            }
        )

    return {
        "name": form.get("name", "").strip(),
        "description": form.get("description", "").strip(),
        "enabled": "1" in form.getlist("enabled"),
        "packages_arch": {
            "present": _lines(form.get("packages_arch_present", "")),
            "absent": _lines(form.get("packages_arch_absent", "")),
        },
        "packages_debian": {
            "present": _lines(form.get("packages_debian_present", "")),
            "absent": _lines(form.get("packages_debian_absent", "")),
        },
        "config_files": config_files,
        "services": services,
        "params": params,
    }


# ── Apply-Routen (Form-Submit aus Modal) ──────────────────────────────────


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def templates_create(request: Request):
    data = await _parse_form(request)
    if not data["name"]:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(tpl={**data, "id": None}, error="Name ist ein Pflichtfeld."),
            status_code=422,
        )
    template_id = uuid.uuid4().hex[:12]
    engine.create_template(template_id, data)
    return render(request, "content.html", _list_ctx())


@router.post(f"/ui/{KEY}/{{template_id}}/update", response_class=HTMLResponse)
async def templates_update(template_id: str, request: Request):
    data = await _parse_form(request)
    if not data["name"]:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(tpl={**data, "id": template_id}, error="Name ist ein Pflichtfeld."),
            status_code=422,
        )
    engine.update_template(template_id, data)
    return render(request, "content.html", _list_ctx())


# ── API-Routen ─────────────────────────────────────────────────────────────


@api_router.get("/for-select")
def for_select():
    return {"options": engine.templates_for_select()}


@api_router.delete("/{template_id}", status_code=204)
def templates_delete(template_id: str):
    engine.delete_template(template_id)
    return Response(status_code=204)


@api_router.patch("/{template_id}/toggle", status_code=204)
def templates_toggle(template_id: str):
    engine.toggle_template(template_id)
    return Response(status_code=204)

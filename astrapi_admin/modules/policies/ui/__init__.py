# astrapi_admin/modules/policies/ui/__init__.py
"""FastAPI-Router fuer den Policy-Editor -- eigener, strukturierter Dialog
statt generischem crud_blueprint (analog zum Haeufigkeit-Picker im
scheduler-Modul), weil Pakete/Config-Dateien/Services jeweils eigene
Tabellen-/Listen-Widgets brauchen, kein simples Formularfeld-Set."""
import uuid

from astrapi_core.ui.controls import Col, ContentTable
from astrapi_core.ui.page_factory import register_content_renderer
from astrapi_core.ui.render import render, render_string
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.policies import engine
from astrapi_admin.modules.templates import engine as templates_engine

KEY = "policies"
_C_ID = f"mod-{KEY}"
_L_ID = f"{KEY}-loading"

router = APIRouter()
api_router = APIRouter()

policies_table = ContentTable(
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


def _summary(p: dict) -> str:
    if p.get("template_id"):
        tpl = templates_engine.get_template(p["template_id"])
        return f"Vorlage: {tpl.get('name') or p['template_id']}" if tpl else "Vorlage: gelöscht"
    n_pkg = (
        len((p.get("packages_arch") or {}).get("present") or [])
        + len((p.get("packages_arch") or {}).get("absent") or [])
        + len((p.get("packages_debian") or {}).get("present") or [])
        + len((p.get("packages_debian") or {}).get("absent") or [])
    )
    parts = []
    if n_pkg:
        parts.append(f"{n_pkg} Pakete")
    if p.get("config_files"):
        parts.append(f"{len(p['config_files'])} Configs")
    if p.get("services"):
        parts.append(f"{len(p['services'])} Services")
    return ", ".join(parts) or "leer"


def _list_ctx() -> dict:
    policies = engine.list_policies()
    return {
        "module": KEY,
        "cfg": {pid: {**p, "summary": _summary(p)} for pid, p in policies.items()},
        "container_id": _C_ID,
        "loading_id": _L_ID,
    }


def _render_content(request):
    return render_string(request, "content.html", _list_ctx())


register_content_renderer(KEY, _render_content)


# ── Liste ────────────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def policies_content(request: Request):
    return render(request, "content.html", _list_ctx())


# ── Dialoge ──────────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/new", response_class=HTMLResponse)
def policies_new(request: Request):
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(policy=None, error=None, templates=templates_engine.list_templates()),
    )


@router.get(f"/ui/{KEY}/{{policy_id}}/edit", response_class=HTMLResponse)
def policies_edit(policy_id: str, request: Request):
    policy = engine.get_policy(policy_id)
    if policy is None:
        return HTMLResponse("", status_code=404)
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(
            policy={**policy, "id": policy_id},
            error=None,
            templates=templates_engine.list_templates(),
        ),
    )


@router.get(f"/ui/{KEY}/{{policy_id}}/delete", response_class=HTMLResponse)
def policies_delete_modal(policy_id: str, request: Request):
    policy = engine.get_policy(policy_id)
    return render(
        request,
        "dialog_confirm.html",
        dict(
            title="Löschen",
            description=policy.get("name", policy_id) if policy else policy_id,
            verb="löschen",
            confirm_url=f"/api/{KEY}/{policy_id}",
            method="delete",
            reload_url=f"/ui/{KEY}/content",
        ),
    )


@router.get(f"/ui/{KEY}/{{policy_id}}/toggle", response_class=HTMLResponse)
def policies_toggle_modal(policy_id: str, request: Request):
    policy = engine.get_policy(policy_id) or {}
    enabled = request.query_params.get("enabled", "True")
    verb = "deaktivieren" if enabled == "True" else "aktivieren"
    return render(
        request,
        "dialog_confirm.html",
        dict(
            description=policy.get("name", policy_id),
            verb=verb,
            confirm_url=f"/api/{KEY}/{policy_id}/toggle",
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

    template_params = {k[3:]: v for k, v in form.multi_items() if k.startswith("tp_")}

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
        "template_id": form.get("template_id", "").strip() or None,
        "template_params": template_params,
    }


# ── Apply-Routen (Form-Submit aus Modal) ──────────────────────────────────


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def policies_create(request: Request):
    data = await _parse_form(request)
    if not data["name"]:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(
                policy={**data, "id": None},
                error="Name ist ein Pflichtfeld.",
                templates=templates_engine.list_templates(),
            ),
            status_code=422,
        )
    policy_id = uuid.uuid4().hex[:12]
    engine.create_policy(policy_id, data)
    return render(request, "content.html", _list_ctx())


@router.post(f"/ui/{KEY}/{{policy_id}}/update", response_class=HTMLResponse)
async def policies_update(policy_id: str, request: Request):
    data = await _parse_form(request)
    if not data["name"]:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(
                policy={**data, "id": policy_id},
                error="Name ist ein Pflichtfeld.",
                templates=templates_engine.list_templates(),
            ),
            status_code=422,
        )
    engine.update_policy(policy_id, data)
    return render(request, "content.html", _list_ctx())


# ── API-Routen ─────────────────────────────────────────────────────────────


@api_router.get("/for-select")
def for_select():
    return {"options": engine.policies_for_select()}


@api_router.delete("/{policy_id}", status_code=204)
def policies_delete(policy_id: str):
    engine.delete_policy(policy_id)
    return Response(status_code=204)


@api_router.patch("/{policy_id}/toggle", status_code=204)
def policies_toggle(policy_id: str):
    engine.toggle_policy(policy_id)
    return Response(status_code=204)

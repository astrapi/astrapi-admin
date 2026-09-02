# astrapi_admin/modules/user_policies/ui/__init__.py
"""FastAPI-Router fuer den Nutzer-Policy-Editor -- eigener,
strukturierter Dialog statt generischem crud_blueprint (analog zu
modules/policies/ui/__init__.py), weil Nutzer-Eintraege ein eigenes
Listen-Widget brauchen, kein simples Formularfeld-Set."""
import uuid

from astrapi_core.ui.controls import Col, ContentTable
from astrapi_core.ui.page_factory import register_content_renderer
from astrapi_core.ui.render import render, render_string
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.user_policies import engine

KEY = "user_policies"
_C_ID = f"mod-{KEY}"
_L_ID = f"{KEY}-loading"

router = APIRouter()
api_router = APIRouter()

user_policies_table = ContentTable(
    has_create=False,
    has_run_buttons=False,
    has_status=False,
    has_toggle=True,
    columns=[
        Col.trunc("description_text", "Beschreibung"),
        Col.text("summary", "Umfang", css="col-info", sortable=False),
    ],
)


def _summary(p: dict) -> str:
    n = len(p.get("entries") or [])
    if not n:
        return "leer"
    return f"{n} Nutzer" if n != 1 else "1 Nutzer"


def _list_item(pid: str, p: dict) -> dict:
    """list_wrapper_inner.html rendert die NAME-Spalte immer fest aus
    item_data.description -- dieselbe Kollisionsklasse wie bei
    policies/host_groups (siehe T-285/T-288/T-291-ADMIN), hier von
    Anfang an vermieden statt erst nachtraeglich gefixt."""
    return {
        **p,
        "summary": _summary(p),
        "description_text": p.get("description") or "—",
        "description": p.get("name") or pid,
    }


def _list_ctx() -> dict:
    policies = engine.list_user_policies()
    return {
        "module": KEY,
        "cfg": {pid: _list_item(pid, p) for pid, p in policies.items()},
        "container_id": _C_ID,
        "loading_id": _L_ID,
    }


def _render_content(request):
    return render_string(request, "content.html", _list_ctx())


register_content_renderer(KEY, _render_content)


# ── Liste ────────────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def user_policies_content(request: Request):
    return render(request, "content.html", _list_ctx())


# ── Dialoge ──────────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/new", response_class=HTMLResponse)
def user_policies_new(request: Request):
    return render(request, f"{KEY}/dialogs/edit/modal.html", dict(policy=None, error=None))


@router.get(f"/ui/{KEY}/{{policy_id}}/edit", response_class=HTMLResponse)
def user_policies_edit(policy_id: str, request: Request):
    policy = engine.get_user_policy(policy_id)
    if policy is None:
        return HTMLResponse("", status_code=404)
    policy = {**policy, "id": policy_id}
    return render(request, f"{KEY}/dialogs/edit/modal.html", dict(policy=policy, error=None))


@router.get(f"/ui/{KEY}/{{policy_id}}/delete", response_class=HTMLResponse)
def user_policies_delete_modal(policy_id: str, request: Request):
    policy = engine.get_user_policy(policy_id)
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
def user_policies_toggle_modal(policy_id: str, request: Request):
    policy = engine.get_user_policy(policy_id) or {}
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

    usernames = form.getlist("ue_username")
    actions = form.getlist("ue_action")
    shells = form.getlist("ue_shell")
    sudos = form.getlist("ue_sudo")
    ssh_keys_raw = form.getlist("ue_ssh_keys")
    entries = []
    for i, username in enumerate(usernames):
        username = username.strip()
        if not username:
            continue
        keys_text = ssh_keys_raw[i] if i < len(ssh_keys_raw) else ""
        entries.append(
            {
                "username": username,
                "action": actions[i] if i < len(actions) else "enforce",
                "shell": (shells[i] if i < len(shells) else "").strip() or "/bin/bash",
                "sudo": (sudos[i] if i < len(sudos) else "0") == "1",
                "ssh_keys": [ln.strip() for ln in keys_text.splitlines() if ln.strip()],
            }
        )

    return {
        "name": form.get("name", "").strip(),
        "description": form.get("description", "").strip(),
        "enabled": "1" in form.getlist("enabled"),
        "entries": entries,
    }


# ── Apply-Routen (Form-Submit aus Modal) ──────────────────────────────────


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def user_policies_create(request: Request):
    data = await _parse_form(request)
    if not data["name"]:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(policy={**data, "id": None}, error="Name ist ein Pflichtfeld."),
            status_code=422,
        )
    policy_id = uuid.uuid4().hex[:12]
    engine.create_user_policy(policy_id, data)
    return render(request, "content.html", _list_ctx())


@router.post(f"/ui/{KEY}/{{policy_id}}/update", response_class=HTMLResponse)
async def user_policies_update(policy_id: str, request: Request):
    data = await _parse_form(request)
    if not data["name"]:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(policy={**data, "id": policy_id}, error="Name ist ein Pflichtfeld."),
            status_code=422,
        )
    engine.update_user_policy(policy_id, data)
    return render(request, "content.html", _list_ctx())


# ── API-Routen ─────────────────────────────────────────────────────────────


@api_router.get("/for-select")
def for_select():
    return {"options": engine.user_policies_for_select()}


@api_router.delete("/{policy_id}", status_code=204)
def user_policies_delete(policy_id: str):
    engine.delete_user_policy(policy_id)
    return Response(status_code=204)


@api_router.patch("/{policy_id}/toggle", status_code=204)
def user_policies_toggle(policy_id: str):
    engine.toggle_user_policy(policy_id)
    return Response(status_code=204)

# astrapi_admin/modules/policies/ui/__init__.py
"""FastAPI-Router fuer den Policy-Editor -- eigener, strukturierter Dialog
statt generischem crud_blueprint (analog zum Haeufigkeit-Picker im
scheduler-Modul), weil Pakete/Config-Dateien/Services jeweils eigene
Tabellen-/Listen-Widgets brauchen, kein simples Formularfeld-Set."""
import json
import re
import uuid

from astrapi_core.system.secrets import get_secret_safe, set_secret
from astrapi_core.ui.controls import Col, ContentTable
from astrapi_core.ui.page_factory import register_content_renderer
from astrapi_core.ui.render import render, render_string
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.policies import engine

KEY = "policies"
_C_ID = f"mod-{KEY}"
_L_ID = f"{KEY}-loading"

router = APIRouter()
api_router = APIRouter()

policies_table = ContentTable(
    has_create=False,
    has_run_buttons=False,
    # Policies "laufen" nicht (kein last_status wie bei Jobs/Scheduler) --
    # die generische Status-Spalte aus list_wrapper_inner.html zeigte
    # deshalb fuer jede Policy nur den bedeutungslosen "Neu"-Default-Badge.
    # Gleiche Fehlerklasse wie bei hosts, siehe T-285-ADMIN.
    has_status=False,
    has_toggle=True,
    columns=[
        Col.trunc("description_text", "Beschreibung"),
        Col.text("summary", "Umfang", sortable=False),
        Col.badge_enum(
            "group_only", "Typ",
            {"Gruppe": {"label": "Gruppe", "cls": "badge-blue"}, "Host": {"label": "Host", "cls": "badge-grey"}},
            css="col-info",
        ),
    ],
)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _slug(text: str) -> str:
    """Dateiname-tauglicher Kurzname fuer den Export-Download."""
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", (text or "").strip().lower()).strip("-")
    return text or "policy"


def _summary(p: dict) -> str:
    n_pkg = len(p.get("packages_arch") or []) + len(p.get("packages_debian") or [])
    parts = []
    if n_pkg:
        parts.append(f"{n_pkg} Pakete")
    if p.get("config_files"):
        parts.append(f"{len(p['config_files'])} Configs")
    if p.get("services"):
        parts.append(f"{len(p['services'])} Services")
    return ", ".join(parts) or "leer"


def _with_secret_status(policy_id: str, config_files: list[dict]) -> list[dict]:
    """Haengt secret_is_set (nur ob GESETZT, nie den Wert selbst) an
    secret=true-Eintraege fuers Formular -- Textarea bleibt in
    modal.html immer leer, der Placeholder unterscheidet nur
    'gesetzt, leer lassen zum Behalten' von 'noch nicht gesetzt'."""
    out = []
    for cf in config_files:
        cf = dict(cf)
        if cf.get("secret"):
            cf["secret_is_set"] = bool(get_secret_safe(engine.secret_name(policy_id, cf["path"])))
        out.append(cf)
    return out


def _list_item(pid: str, p: dict) -> dict:
    """list_wrapper_inner.html rendert die NAME-Spalte immer fest aus
    item_data.description (oder .job/.host/item_name) -- Policies haben
    aber ein EIGENES, eigentlich massgebliches 'name'-Feld (Pflichtfeld
    beim Anlegen) UND ein separates, optionales 'description'-Feld fuer
    Fliesstext. Ohne diese Auflösung kollidieren beide: die NAME-Spalte
    zeigte bisher entweder die rohe Policy-ID (description leer) oder
    versehentlich den Beschreibungstext statt des Namens (description
    gesetzt) -- so beim 'caddy'-Eintrag beobachtet. 'description_text'
    ist ein neuer, kollisionsfreier Schluessel eigens fuer die
    Beschreibung-SPALTE (Col.trunc), waehrend 'description' jetzt den
    Policy-Namen fuers eingebaute NAME-Feld traegt."""
    return {
        **p,
        "summary": _summary(p),
        "description_text": p.get("description") or "—",
        "description": p.get("name") or pid,
        # T-305-ADMIN: Col.badge_enum() schaut den Wert NUR nach, wenn er
        # selbst schon truthy ist (siehe ui_macros.html::col_cell) --
        # group_only=False wuerde also nie im 'False'-Eintrag der
        # values-Map landen, sondern immer als "-" gerendert. Deshalb
        # hier auf einen eigenen, immer truthy-String umgeschrieben
        # (analog zu _format_updates_available() in hosts/ui/crud.py).
        "group_only": "Gruppe" if p.get("group_only") else "Host",
    }


def _list_ctx() -> dict:
    policies = engine.list_policies()
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
def policies_content(request: Request):
    return render(request, "content.html", _list_ctx())


# ── Dialoge ──────────────────────────────────────────────────────────────


@router.get(f"/ui/{KEY}/new", response_class=HTMLResponse)
def policies_new(request: Request):
    return render(request, f"{KEY}/dialogs/edit/modal.html", dict(policy=None, error=None))


@router.get(f"/ui/{KEY}/{{policy_id}}/edit", response_class=HTMLResponse)
def policies_edit(policy_id: str, request: Request):
    policy = engine.get_policy(policy_id)
    if policy is None:
        return HTMLResponse("", status_code=404)
    policy = {
        **policy,
        "id": policy_id,
        "config_files": _with_secret_status(policy_id, policy.get("config_files") or []),
    }
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        dict(policy=policy, error=None),
    )


@router.get(f"/ui/{KEY}/{{policy_id}}/export")
def policies_export(policy_id: str):
    """Reiner Download-Link (kein HTMX) -- liefert das rohe, gespeicherte
    Policy-JSON. Enthaelt nie Klartext-Geheimnisse: secret=true-Eintraege
    haben ihr 'content'-Feld im Storage ohnehin immer leer (siehe
    _parse_form() -- der eigentliche Wert liegt getrennt im Secrets-Store,
    ausserhalb dieses Exports). Keine Host-/Gruppen-Zuweisung enthalten,
    die lebt getrennt bei hosts/host_groups."""
    policy = engine.get_policy(policy_id)
    if policy is None:
        return Response(status_code=404)
    filename = f"policy-{_slug(policy.get('name') or policy_id)}.json"
    return Response(
        content=json.dumps(policy, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(f"/ui/{KEY}/import", response_class=HTMLResponse)
def policies_import_modal(request: Request):
    return render(request, f"{KEY}/dialogs/import/modal.html", dict(error=None, raw=None))


@router.post(f"/ui/{KEY}/import-preview", response_class=HTMLResponse)
async def policies_import_preview(request: Request):
    """Legt NICHTS an -- parst nur das eingefuegte JSON und uebergibt es an
    den bestehenden Edit-Dialog (id=None -> is_new, geht beim Absenden
    ueber den normalen policies_create()-Pfad). So bekommt der Nutzer vor
    dem eigentlichen Anlegen noch die Chance, Geheimnisse neu einzutragen
    (die der Export nie enthaelt) und Werte zu pruefen/anzupassen."""
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

    policy = {
        "id": None,
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "enabled": bool(data.get("enabled", True)),
        "group_only": bool(data.get("group_only", False)),
        "packages_arch": _as_list(data.get("packages_arch")),
        "packages_debian": _as_list(data.get("packages_debian")),
        "config_files": _as_list(data.get("config_files")),
        "services": _as_list(data.get("services")),
    }
    return render(request, f"{KEY}/dialogs/edit/modal.html", dict(policy=policy, error=None))


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


async def _parse_form(request: Request, policy_id: str) -> dict:
    """policy_id muss VOR dem Parsen feststehen (bei policies_create() also
    schon vor dem eigentlichen Anlegen erzeugt werden) -- secret=true-Zeilen
    schreiben ihren Klartext direkt unter secret_name(policy_id, path) in
    den Secrets-Store, nie ins zurueckgegebene dict."""
    form = await request.form()

    paths = form.getlist("cf_path")
    actions = form.getlist("cf_action")
    contents = form.getlist("cf_content")
    modes = form.getlist("cf_mode")
    owners = form.getlist("cf_owner")
    groups = form.getlist("cf_group")
    forces = form.getlist("cf_force")
    secret_flags = form.getlist("cf_secret")
    config_files = []
    for i, path in enumerate(paths):
        path = path.strip()
        if not path:
            continue
        is_secret = (secret_flags[i] if i < len(secret_flags) else "0") == "1"
        content = contents[i] if i < len(contents) else ""
        if is_secret:
            # Leer gelassen = bestehenden Wert behalten (wie ein
            # Passwort-Feld) -- nur bei echter Eingabe ueberschreiben.
            if content:
                set_secret(engine.secret_name(policy_id, path), content)
            content = ""
        config_files.append(
            {
                "path": path,
                "action": actions[i] if i < len(actions) else "enforce",
                "content": content,
                "mode": (modes[i] if i < len(modes) else "").strip() or "0644",
                "owner": (owners[i] if i < len(owners) else "").strip() or "root",
                "group": (groups[i] if i < len(groups) else "").strip() or "root",
                "force": (forces[i] if i < len(forces) else "0") == "1",
                "secret": is_secret,
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

    return {
        "name": form.get("name", "").strip(),
        "description": form.get("description", "").strip(),
        "enabled": "1" in form.getlist("enabled"),
        "group_only": "1" in form.getlist("group_only"),
        "packages_arch": _lines(form.get("packages_arch", "")),
        "packages_debian": _lines(form.get("packages_debian", "")),
        "config_files": config_files,
        "services": services,
    }


# ── Apply-Routen (Form-Submit aus Modal) ──────────────────────────────────


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def policies_create(request: Request):
    # policy_id muss vor _parse_form() feststehen -- secret=true-Zeilen
    # brauchen ihn schon beim Parsen fuer den Secrets-Store-Schluessel.
    policy_id = uuid.uuid4().hex[:12]
    data = await _parse_form(request, policy_id)
    if not data["name"]:
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(policy={**data, "id": None}, error="Name ist ein Pflichtfeld."),
            status_code=422,
        )
    engine.create_policy(policy_id, data)
    return render(request, "content.html", _list_ctx())


@router.post(f"/ui/{KEY}/{{policy_id}}/update", response_class=HTMLResponse)
async def policies_update(policy_id: str, request: Request):
    data = await _parse_form(request, policy_id)
    if not data["name"]:
        data["config_files"] = _with_secret_status(policy_id, data["config_files"])
        return render(
            request,
            f"{KEY}/dialogs/edit/modal.html",
            dict(policy={**data, "id": policy_id}, error="Name ist ein Pflichtfeld."),
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

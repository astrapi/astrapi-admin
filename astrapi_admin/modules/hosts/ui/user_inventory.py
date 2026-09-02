# astrapi_admin/modules/hosts/ui/user_inventory.py
"""Read-only Bestandsaufnahme-Dialog fuer die auf einem Host gefundenen
Nutzerkonten (E-012) -- rein informativ, siehe
user_policies/engine.py::resolve_users_for_host() fuer die eigentliche
Durchsetzung."""
import json

from astrapi_core.ui.render import render
from fastapi import Request
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.hosts.ui.crud import KEY, router, store


@router.get(f"/ui/{KEY}/{{item_id}}/user-inventory", response_class=HTMLResponse)
def user_inventory_dialog(item_id: str, request: Request):
    host = store.get(item_id)
    if host is None:
        return HTMLResponse("", status_code=404)
    description = host.get("label") or host.get("hostname") or item_id
    try:
        inventory = json.loads(host.get("user_inventory") or "[]")
    except (ValueError, TypeError):
        inventory = []
    return render(
        request,
        "hosts/dialogs/user_inventory/modal.html",
        dict(
            description=description,
            inventory=inventory,
            checked_at=host.get("user_inventory_checked_at") or "",
        ),
    )

# astrapi_admin/modules/hosts/ui/updates.py
"""Update-Status-Anzeige + explizit ausgeloestes Update pro Host (E-007).

Bewusst NICHT automatisch/Policy-getrieben (siehe [[E-004]]) -- ein
Admin loest hier bewusst EINEN Host aus, kein Bulk-Trigger. Da der
Agent rein Pull-basiert ist (kein Push/SSH-Kanal), wird nur ein
pending_action-Flag gesetzt; der Agent liest es beim naechsten
GET /api/agent/policy und fuehrt das Update dann selbst aus."""
from astrapi_core.ui.render import render
from fastapi import Request, Response
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.hosts.ui.crud import KEY, api_router, router, store


@router.get(f"/ui/{KEY}/{{item_id}}/trigger-update", response_class=HTMLResponse)
def trigger_update_dialog(item_id: str, request: Request):
    host = store.get(item_id)
    if host is None:
        return HTMLResponse("Host nicht gefunden", status_code=404)
    label = host.get("label") or host.get("hostname") or item_id
    return render(
        request,
        "dialog_confirm.html",
        dict(
            title="Update anstoßen",
            description=(
                f"{label}: löst beim nächsten Zyklus ein echtes "
                "'apt upgrade'/'pacman -Syu' auf diesem einen Host aus."
            ),
            verb="aktualisieren",
            confirm_url=f"/api/{KEY}/{item_id}/trigger-update",
            method="patch",
            reload_url=f"/ui/{KEY}/content",
        ),
    )


@api_router.patch("/{item_id}/trigger-update", status_code=204)
def trigger_update(item_id: str):
    store.update(item_id, {"pending_action": "update"})
    return Response(status_code=204)

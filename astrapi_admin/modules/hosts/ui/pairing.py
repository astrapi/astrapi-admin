# astrapi_admin/modules/hosts/ui/pairing.py
"""Admin-Dialog: Pairing-Token fuer einen neuen Host erzeugen und anzeigen."""
from fastapi import Request
from fastapi.responses import HTMLResponse

from astrapi_core.ui.render import render

from astrapi_admin.modules.hosts.pairing_store import create_pairing_token, ttl_seconds
from astrapi_admin.modules.hosts.ui.crud import KEY, router


@router.get(f"/ui/{KEY}/pair", response_class=HTMLResponse)
def pair_dialog(request: Request):
    token = create_pairing_token()
    server_url = str(request.base_url).rstrip("/")
    return render(
        request,
        f"{KEY}/dialogs/pair/modal.html",
        {
            "token": token,
            "server_url": server_url,
            "ttl_minutes": ttl_seconds() // 60,
        },
    )


@router.get(f"/ui/{KEY}/{{item_id}}/reconnect", response_class=HTMLResponse)
def reconnect_dialog(item_id: str, request: Request):
    """Erzeugt einen Pairing-Code, der beim Einloesen NICHT einen neuen Host
    anlegt, sondern nur das Token des bestehenden ersetzt -- Gruppen/Policies
    bleiben unveraendert."""
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host = hosts_store.get(item_id)
    if host is None:
        return HTMLResponse("Host nicht gefunden", status_code=404)

    token = create_pairing_token(host_id=item_id)
    server_url = str(request.base_url).rstrip("/")
    return render(
        request,
        f"{KEY}/dialogs/pair/modal.html",
        {
            "token": token,
            "server_url": server_url,
            "ttl_minutes": ttl_seconds() // 60,
            "host_label": host.get("label") or host.get("hostname"),
        },
    )

# astrapi_admin/modules/hosts/ui/trigger.py
"""Sofort-Poll ueber eine reine TCP-Verbindung zum Trigger-Port des
Agenten (T-322-ADMIN). Kein Push im eigentlichen Sinn -- der Server
schickt keine Daten, das blosse Verbinden auf TRIGGER_PORT reicht als
Signal. astrapi-admin-agent-trigger.socket (systemd-Socket-Aktivierung
auf dem Host) startet bei jeder eingehenden Verbindung direkt
astrapi-admin-agent.service, ohne dass der Agent selbst dafuer
Netzwerkcode braucht -- kein neuer Dauerprozess auf den Hosts.

Bewusst OHNE Authentifizierung (Nutzerentscheidung T-322-ADMIN): der
host_token kann dafuer nicht wiederverwendet werden -- er wird nur
SHA-256-gehasht gespeichert (api/auth.py::hash_token()), der Server
kennt den Klartext-Token nach dem Pairing nicht mehr. Ein separates
Secret waere moeglich gewesen, wurde aber als unverhaeltnismaessig
verworfen: die einzige Wirkung eines unbefugten Trigger-Aufrufs ist ein
vorgezogener, ohnehin regulaerer Poll-Zyklus -- kein Zugriff auf
Policy-Daten, keine Moeglichkeit, Befehle einzuschleusen."""
import logging
import socket

from astrapi_core.ui.render import render
from fastapi import HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.hosts.ui.crud import KEY, api_router, router, store

log = logging.getLogger(__name__)

TRIGGER_PORT = 8765


@router.get(f"/ui/{KEY}/{{item_id}}/trigger-poll", response_class=HTMLResponse)
def trigger_poll_dialog(item_id: str, request: Request):
    host = store.get(item_id)
    if host is None:
        return HTMLResponse("Host nicht gefunden", status_code=404)
    label = host.get("label") or host.get("hostname") or item_id

    return render(
        request,
        "dialog_confirm.html",
        dict(
            title="Jetzt pollen",
            description=f"{label} -- fordert den Agenten auf, sofort einen Policy-Zyklus "
            "auszuführen, statt auf den nächsten regulären Poll zu warten. "
            "Braucht mindestens astrapi-admin-agent v26.9.8.",
            verb="pollen",
            confirm_url=f"/api/{KEY}/{item_id}/trigger-poll",
            method="patch",
            reload_url=f"/ui/{KEY}/content",
        ),
    )


@api_router.patch("/{item_id}/trigger-poll", status_code=204)
def trigger_poll(item_id: str):
    from astrapi_core.system.activity_log import log_activity

    host = store.get(item_id)
    if host is None:
        raise HTTPException(404, "Host nicht gefunden")
    label = host.get("label") or host.get("hostname") or item_id
    hostname = host.get("hostname") or ""

    try:
        with socket.create_connection((hostname, TRIGGER_PORT), timeout=5):
            pass
    except OSError as e:
        log_activity(
            log_type="job",
            module="hosts",
            item_id=str(item_id),
            description=f"Sofort-Poll für „{label}“ fehlgeschlagen: {e}",
            status="error",
        )
        raise HTTPException(502, f"Trigger fehlgeschlagen: {e}") from e

    log_activity(
        log_type="job",
        module="hosts",
        item_id=str(item_id),
        description=f"Sofort-Poll für „{label}“ ausgelöst",
        status="ok",
    )
    return Response(status_code=204)

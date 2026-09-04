# astrapi_admin/modules/hosts/ui/updates.py
"""Update-Status-Anzeige + explizit ausgeloestes Update pro Host (E-007),
optional mit vorausgehendem Proxmox-Snapshot (E-009).

Bewusst NICHT automatisch/Policy-getrieben (siehe [[E-004]]) -- ein
Admin loest hier bewusst EINEN Host aus, kein Bulk-Trigger. Da der
Agent rein Pull-basiert ist (kein Push/SSH-Kanal), wird nur ein
pending_action-Flag gesetzt; der Agent liest es beim naechsten
GET /api/agent/policy und fuehrt das Update dann selbst aus."""
import logging
import time

from astrapi_core.ui.render import render
from fastapi import HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.hosts.ui.crud import KEY, api_router, router, store

log = logging.getLogger(__name__)


def _pending_packages_list(host: dict) -> tuple[list[str] | None, str | None]:
    """T-284-ADMIN: (items_list, items_label) fuer die scrollbare
    Paketvorschau im Bestaetigungsdialog -- die Liste stammt aus dem
    letzten regulaeren Report (post_report()), ist also hoechstens so
    aktuell wie der letzte Agent-Zyklus, nicht live zum Zeitpunkt des
    Klicks. items_list bleibt None, wenn nichts Bekanntes anzuzeigen ist
    -- dann rendert dialog_confirm.html die Box gar nicht erst."""
    packages = host.get("updates_package_list") or []
    if not packages:
        return None, None

    security = set(host.get("security_updates_package_list") or [])
    labeled = [f"{p} (sicherheitsrelevant)" if p in security else p for p in packages]
    label = f"{len(packages)} Update{'s' if len(packages) != 1 else ''} betroffen:"
    return labeled, label


@router.get(f"/ui/{KEY}/{{item_id}}/trigger-update", response_class=HTMLResponse)
def trigger_update_dialog(item_id: str, request: Request):
    host = store.get(item_id)
    if host is None:
        return HTMLResponse("Host nicht gefunden", status_code=404)
    label = host.get("label") or host.get("hostname") or item_id

    items_list, items_label = _pending_packages_list(host)
    description = label
    if items_list is None:
        description += " (keine bekannten ausstehenden Updates -- evtl. noch nicht geprüft)"
    if host.get("snapshot_before_update") and (host.get("proxmox_vmid") or -1) >= 0:
        description += " -- vorher wird ein Proxmox-Snapshot erstellt; schlägt der fehl, wird kein Update ausgelöst"

    return render(
        request,
        "dialog_confirm.html",
        dict(
            title="Update anstoßen",
            description=description,
            verb="aktualisieren",
            items_list=items_list,
            items_label=items_label,
            confirm_url=f"/api/{KEY}/{item_id}/trigger-update",
            method="patch",
            reload_url=f"/ui/{KEY}/content",
        ),
    )


def _create_pre_update_snapshot(host: dict) -> tuple[bool, str]:
    """Loest den Snapshot live per Hostname-Abgleich aus (nicht ueber die
    zwischengespeicherte proxmox_vmid, siehe E-009) -- robuster gegen
    Live-Migration zwischen Proxmox-Nodes und einen zwischenzeitlich
    veraenderten/geloeschten Container."""
    from astrapi_admin.modules.hosts import proxmox_client

    found = proxmox_client.find_lxc_by_hostname(host.get("hostname") or "")
    if found is None:
        return False, "Proxmox-LXC nicht (mehr) gefunden"
    if proxmox_client.is_vzdump_running(found["node"], found["vmid"]):
        # E-010: Koordination mit astrapi-backups proxmox_lxc-Modul --
        # ein Snapshot-Versuch waehrend eines laufenden vzdump wuerde bei
        # Proxmox ohnehin an dessen eigener Pro-VMID-Sperre scheitern,
        # hier aber mit einer klaren Meldung statt einem rohen Lock-Fehler.
        return False, "Backup läuft gerade auf diesem Host -- bitte später erneut versuchen"
    snapname = f"astrapi-admin-preupdate-{time.strftime('%Y%m%d-%H%M%S')}"
    return proxmox_client.create_snapshot(found["node"], found["vmid"], snapname)


@api_router.patch("/{item_id}/trigger-update", status_code=204)
def trigger_update(item_id: str):
    from astrapi_core.system.activity_log import log_activity

    host = store.get(item_id)
    if host is None:
        raise HTTPException(404, "Host nicht gefunden")
    label = host.get("label") or host.get("hostname") or item_id

    if host.get("snapshot_before_update") and (host.get("proxmox_vmid") or -1) >= 0:
        ok, detail = _create_pre_update_snapshot(host)
        if not ok:
            log_activity(
                log_type="job",
                module="hosts",
                item_id=str(item_id),
                description=f"Snapshot vor Update für „{label}“ fehlgeschlagen -- Update NICHT ausgelöst: {detail}",
                status="error",
            )
            try:
                from astrapi_core.modules.notify import engine as notify_engine

                notify_engine.send(
                    title=f"{label}: Snapshot vor Update fehlgeschlagen",
                    message=f"Update wurde NICHT ausgelöst. Grund: {detail}",
                    event=notify_engine.ERROR,
                    source="hosts",
                    tags=["update", "snapshot"],
                )
            except Exception as e:
                log.warning("notify: Benachrichtigung für Snapshot-Fehlschlag fehlgeschlagen: %s", e)
            raise HTTPException(502, f"Snapshot fehlgeschlagen, Update NICHT ausgelöst: {detail}")

    store.update(item_id, {"pending_action": "update"})
    return Response(status_code=204)


@router.get(f"/ui/{KEY}/{{item_id}}/cancel-update", response_class=HTMLResponse)
def cancel_update_dialog(item_id: str, request: Request):
    host = store.get(item_id)
    if host is None:
        return HTMLResponse("Host nicht gefunden", status_code=404)
    label = host.get("label") or host.get("hostname") or item_id

    return render(
        request,
        "dialog_confirm.html",
        dict(
            title="Update zurücknehmen",
            description=f"{label} -- das angeforderte Update wird nicht mehr ausgeführt, "
            "solange es der Agent noch nicht abgeholt hat.",
            verb="zurücknehmen",
            confirm_url=f"/api/{KEY}/{item_id}/cancel-update",
            method="patch",
            reload_url=f"/ui/{KEY}/content",
        ),
    )


@api_router.patch("/{item_id}/cancel-update", status_code=204)
def cancel_update(item_id: str):
    """Setzt pending_action nur zurueck, wenn noch 'update' ansteht -- ein
    Agent, der die Anforderung zwischen Klick und Bestaetigung bereits
    abgeholt hat (pending_action dadurch schon wieder leer, siehe
    post_report() in api/agent.py), soll durch einen verspaeteten
    Abbruch-Klick nicht faelschlich etwas ueberschreiben."""
    host = store.get(item_id)
    if host is None:
        raise HTTPException(404, "Host nicht gefunden")

    if host.get("pending_action") == "update":
        store.update(item_id, {"pending_action": ""})
    return Response(status_code=204)

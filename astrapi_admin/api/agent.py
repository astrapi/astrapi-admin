"""astrapi_admin.api.agent – Agent-seitige API (Pairing, Policy-Abruf, Report)."""
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from astrapi_admin.api.auth import hash_token, require_host

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


_REPORT_STATUSES = {"ok", "drift", "error", "conflict"}


class PairRequest(BaseModel):
    token: str
    hostname: str = ""
    os_type: str = ""


class ReportRequest(BaseModel):
    status: str = "ok"
    summary: str = ""
    details: dict = {}


@router.post("/pair")
def pair(payload: PairRequest):
    from astrapi_core.system.activity_log import log_activity

    from astrapi_admin.modules.hosts.pairing_store import redeem_pairing_token
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    pairing_info = redeem_pairing_token(payload.token)
    if pairing_info is None:
        raise HTTPException(400, "Ungültiger oder abgelaufener Pairing-Code")

    host_token = secrets.token_urlsafe(32)
    existing_host_id = pairing_info.get("host_id")

    if existing_host_id is not None:
        # Neu verbinden: nur das Token ersetzen, Gruppen/Policies/Label
        # bleiben unangetastet (siehe hosts/ui/pairing.py::reconnect_dialog).
        existing = hosts_store.get(existing_host_id)
        if existing is None:
            raise HTTPException(404, "Host wurde inzwischen gelöscht")
        hosts_store.update(existing_host_id, {"token_hash": hash_token(host_token)})
        log_activity(
            log_type="job",
            module="hosts",
            item_id=str(existing_host_id),
            description=f"Host „{existing.get('label') or existing.get('hostname') or existing_host_id}“ neu verbunden",
            status="ok",
        )
        return {
            "host_id": existing_host_id,
            "host_token": host_token,
            "group_ids": existing.get("group_ids") or [],
            "policy_ids": existing.get("policy_ids") or [],
        }

    hostname = payload.hostname or "unbekannt"
    item_id = hosts_store.create(
        None,
        {
            "hostname": hostname,
            "label": hostname,
            "os_type": payload.os_type or "",
            "group_ids": [],
            "policy_ids": [],
            "token_hash": hash_token(host_token),
            "last_seen": "",
            "last_report": "",
            "last_status": "",
            "enabled": True,
        },
    )
    log_activity(
        log_type="job",
        module="hosts",
        item_id=str(item_id),
        description=f"Neuer Host „{hostname}“ gepairt",
        status="ok",
    )

    return {
        "host_id": item_id,
        "host_token": host_token,
        "group_ids": [],
        "policy_ids": [],
    }


@router.get("/policy")
def get_policy(host_data=Depends(require_host)):
    from astrapi_admin.modules.hosts.mirror_repos import resolve_mirror_config_files
    from astrapi_admin.modules.policies.engine import resolve_policy_for_host

    _host_id, host = host_data
    result = resolve_policy_for_host(host)
    resolve_mirror_config_files(host, result)
    # E-007: rein informativ fuer den Agenten, welche einmalige Aktion
    # der Admin explizit angefordert hat (aktuell nur "update") -- NICHT
    # automatisch/Policy-getrieben, siehe hosts/ui/updates.py.
    result["pending_action"] = host.get("pending_action") or ""
    return result


def _notify_new_updates(host_id, host: dict, details: dict) -> None:
    """Benachrichtigt (falls in astrapi-core::notify konfiguriert) nur
    wenn sich die gemeldete Update-Anzahl gegenueber dem zuletzt
    bekannten Stand ERHOEHT hat (E-008) -- sonst wuerde bei jedem
    15-Minuten-Zyklus dieselbe unveraenderte Zahl erneut gemeldet.
    Sicherheitsrelevante Updates gehen als WARNING raus (hoehere
    Prioritaet, siehe notify.engine._PRIORITY_MAP), rein normale als
    INFO -- pro Report nur eine der beiden, nicht beide gleichzeitig
    (WARNING schliesst den Normalfall bereits mit ein)."""
    label = host.get("label") or host.get("hostname") or str(host_id)
    new_total = details.get("updates_available", 0)
    new_security = details.get("security_updates_available")
    old_total = host.get("updates_available", -1)
    old_security = host.get("security_updates_available", -1)

    try:
        from astrapi_core.modules.notify import engine as notify_engine

        if new_security is not None and new_security > 0 and new_security > max(old_security, 0):
            notify_engine.send(
                title=f"{label}: sicherheitsrelevante Updates verfügbar",
                message=f"{new_security} von {new_total} verfügbaren Updates sind sicherheitsrelevant.",
                event=notify_engine.WARNING,
                source="hosts",
                tags=["update", "security"],
            )
        elif new_total > 0 and new_total > max(old_total, 0):
            notify_engine.send(
                title=f"{label}: Updates verfügbar",
                message=f"{new_total} Update{'s' if new_total != 1 else ''} verfügbar.",
                event=notify_engine.INFO,
                source="hosts",
                tags=["update"],
            )
    except Exception as e:
        log.warning("notify: Benachrichtigung für Update-Status fehlgeschlagen (Host %s): %s", host_id, e)


@router.post("/report")
def post_report(payload: ReportRequest, host_data=Depends(require_host)):
    import json

    from astrapi_core.system.activity_log import log_activity

    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, host = host_data
    status = payload.status if payload.status in _REPORT_STATUSES else "error"

    import time

    updates = {
        "last_report": json.dumps({"status": status, "summary": payload.summary, "details": payload.details}),
        "last_status": status,
    }
    if "updates_available" in payload.details:
        updates["updates_available"] = payload.details["updates_available"]
        updates["updates_checked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if "security_updates_available" in payload.details:
            updates["security_updates_available"] = payload.details["security_updates_available"]
        _notify_new_updates(host_id, host, payload.details)
    if "update_result" in payload.details:
        # E-007: die angeforderte Aktion wurde versucht (egal ob
        # erfolgreich) -- pending_action zuruecksetzen, sonst bliebe ein
        # fehlgeschlagenes Update fuer immer "pending" und wuerde bei
        # jedem Zyklus stumpf wiederholt.
        updates["pending_action"] = ""

    hosts_store.update(host_id, updates)

    log_activity(
        log_type="job",
        module="hosts",
        item_id=str(host_id),
        description=payload.summary or f"Policy-Report von „{host.get('label') or host.get('hostname') or host_id}“",
        status=status,
    )

    return {"ok": True}

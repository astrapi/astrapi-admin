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
    return result


@router.post("/report")
def post_report(payload: ReportRequest, host_data=Depends(require_host)):
    import json

    from astrapi_core.system.activity_log import log_activity

    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, host = host_data
    status = payload.status if payload.status in _REPORT_STATUSES else "error"

    hosts_store.update(
        host_id,
        {
            "last_report": json.dumps({"status": status, "summary": payload.summary, "details": payload.details}),
            "last_status": status,
        },
    )

    log_activity(
        log_type="job",
        module="hosts",
        item_id=str(host_id),
        description=payload.summary or f"Policy-Report von „{host.get('label') or host.get('hostname') or host_id}“",
        status=status,
    )

    return {"ok": True}

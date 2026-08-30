# astrapi_admin/api/auth.py
"""Host-Authentifizierung fuer die Agent-API.

astrapi-core kennt keinerlei Auth-Konzept -- komplett neu, 1:1 nach
astrapi_sync/api/auth.py portiert (SHA-256-Hash + hmac.compare_digest,
Bearer-Token, last_seen wird bei jedem authentifizierten Call
aktualisiert statt ueber einen eigenen Heartbeat-Endpunkt). Anders als
bei sync gibt es keinen folder_id-Sonderfall -- ein Host holt immer nur
seine eigene Policy, keine Pfad-Scopes noetig.
"""
import hashlib
import hmac
import time

from fastapi import Header, HTTPException


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_host_by_token(token: str) -> tuple[str, dict] | None:
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    token_hash = hash_token(token)
    for host_id, host in hosts_store.list().items():
        # hmac.compare_digest() statt "==" -- schliesst Timing-Seitenkanaele
        # beim Hash-Vergleich aus (gleiche Lektion wie astrapi-sync).
        if hmac.compare_digest(host.get("token_hash") or "", token_hash):
            return host_id, host
    return None


def authenticate(token: str) -> tuple[str, dict]:
    """Prueft ein rohes Token (ohne "Bearer "-Praefix), aktualisiert last_seen.

    Gibt (host_id, host_dict) zurueck oder wirft HTTPException.
    """
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    found = get_host_by_token(token)
    if found is None:
        raise HTTPException(401, "Ungültiges Host-Token")
    host_id, host = found
    if not host.get("enabled", True):
        raise HTTPException(403, "Host ist deaktiviert")

    hosts_store.update(host_id, {"last_seen": time.strftime("%Y-%m-%d %H:%M:%S")})
    return host_id, host


def require_host(authorization: str = Header(default="")) -> tuple[str, dict]:
    """Dependency fuer alle /api/agent/...-Endpunkte (ausser pair)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Kein Host-Token angegeben")
    return authenticate(authorization.removeprefix("Bearer ").strip())

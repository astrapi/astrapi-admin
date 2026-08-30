# astrapi_admin/modules/hosts/pairing_store.py
"""In-Memory-Speicher fuer kurzlebige Pairing-Tokens.

1:1 nach astrapi_sync/modules/devices/pairing_store.py -- bewusst nicht in
der DB: Pairing-Tokens sind einmalig, laufen nach 10 Minuten ab und
muessen keinen Neustart ueberleben.

Zwei Varianten:
- Neuer Host (host_id=None): /api/agent/pair legt eine neue hosts-Zeile an.
- Neu verbinden (host_id gesetzt): /api/agent/pair ersetzt nur das Token
  EINES bestehenden Hosts -- Policies/Gruppen bleiben unangetastet.
"""

import secrets
import time

_TTL_SECONDS = 600

# token -> {"created_at": float, "host_id": str | None}
_pending: dict[str, dict] = {}


def create_pairing_token(host_id: str | None = None) -> str:
    _cleanup()
    token = secrets.token_urlsafe(24)
    _pending[token] = {"created_at": time.time(), "host_id": host_id}
    return token


def redeem_pairing_token(token: str) -> dict | None:
    """Entfernt den Token (Einmal-Nutzung) und gibt seine Metadaten zurueck,
    oder None wenn er ungueltig/abgelaufen ist."""
    _cleanup()
    return _pending.pop(token, None)


def _cleanup() -> None:
    now = time.time()
    expired = [t for t, meta in _pending.items() if now - meta["created_at"] > _TTL_SECONDS]
    for t in expired:
        _pending.pop(t, None)


def ttl_seconds() -> int:
    return _TTL_SECONDS

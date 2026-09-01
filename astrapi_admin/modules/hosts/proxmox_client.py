# astrapi_admin/modules/hosts/proxmox_client.py
"""HTTP-Client gegen die Proxmox-API -- Grundlage fuer "Snapshot vor
Update" (E-009). Bewusst fehlertolerant wie mirror_client.py: eine nicht
konfigurierte/kurz nicht erreichbare Proxmox-API darf weder das Pairing
noch den normalen Betrieb zum Absturz bringen -- nur der tatsaechliche
Snapshot-vor-Update-Aufruf (create_snapshot(), aus hosts/ui/updates.py)
blockiert bei einem Fehler bewusst das Update, alles andere hier ist
best-effort.

Auth: Proxmox API-Token (Header 'PVEAPIToken=<token_id>=<token_secret>'),
kein Login/Cookie-Flow noetig. Token-Secret liegt ueber den eingebauten
'type: password'-Mechanismus der astrapi-core-Settings-Engine
(astrapi_core.modules.settings.ui::settings_save_module()) verschluesselt
in astrapi_core.system.secrets -- kein eigener Code dafuer noetig, siehe
[[E-006]]-Vorbild (dort noch handgebaut, hier bereits eingebaut).

WICHTIG: bislang NICHT gegen eine echte Proxmox-Instanz verifiziert
(keine in dieser Sandbox verfuegbar) -- Endpunkt-Formen und Antwort-
Struktur folgen der oeffentlich dokumentierten Proxmox-VE-API, aber ohne
den sonst in dieser Session ueblichen echten Verifikations-Schritt
(vgl. Docker-Verifikation bei apt/pacman-contrib). Vor Produktiveinsatz
gegen die echte Proxmox-Instanz des Nutzers testen."""
import ssl
import time

import httpx

_TIMEOUT = 10.0
_SSL_CONTEXT = ssl.create_default_context()

# Wie lange maximal auf den Abschluss des asynchronen Proxmox-Snapshot-
# Tasks gewartet wird, bevor create_snapshot() aufgibt -- LXC-Snapshots
# sind normalerweise binnen weniger Sekunden fertig.
_SNAPSHOT_MAX_WAIT_S = 60
_SNAPSHOT_POLL_INTERVAL_S = 2


def _base_url() -> str:
    from astrapi_core.ui.settings_registry import get_module

    return (get_module("hosts", "proxmox_base_url", "") or "").rstrip("/")


def _auth_header() -> dict | None:
    from astrapi_core.system.secrets import get_secret_safe
    from astrapi_core.ui.settings_registry import get_module

    base = _base_url()
    token_id = get_module("hosts", "proxmox_token_id", "") or ""
    token_secret = get_secret_safe("module.hosts.proxmox_token_secret")
    if not base or not token_id or not token_secret:
        return None
    return {"Authorization": f"PVEAPIToken={token_id}={token_secret}"}


def configured() -> bool:
    return _auth_header() is not None


def is_vzdump_running(node: str, vmid: int) -> bool:
    """Prueft, ob gerade ein vzdump-Backup fuer diese VMID laeuft (E-010
    -- Koordination mit astrapi-backups proxmox_lxc-Modul, das denselben
    Proxmox-Cluster fuer LXC-Backups nutzt). Best-effort: False bei
    jedem Fehler -- ein kurzzeitig nicht erreichbares Proxmox soll das
    Update nicht dauerhaft blockieren; das eigentliche Sicherheitsnetz
    ist ohnehin Proxmox' eigene Sperre pro VMID beim tatsaechlichen
    Snapshot-Versuch."""
    headers = _auth_header()
    if headers is None:
        return False
    base = _base_url()
    try:
        r = httpx.get(
            f"{base}/api2/json/nodes/{node}/tasks",
            params={"vmid": vmid, "running": 1, "typefilter": "vzdump"},
            headers=headers,
            timeout=_TIMEOUT,
            verify=_SSL_CONTEXT,
        )
        r.raise_for_status()
        return len(r.json().get("data", [])) > 0
    except (httpx.HTTPError, ValueError):
        return False


def find_lxc_by_hostname(hostname: str) -> dict | None:
    """Sucht im gesamten Proxmox-Cluster nach einem LXC-Container, dessen
    'name' (bei LXC == der tatsaechliche Hostname im Container, anders
    als bei QEMU-VMs) exakt passt. Liefert {'vmid': int, 'node': str}
    oder None (nicht konfiguriert, nicht erreichbar, oder kein Treffer --
    alle drei Faelle bewusst gleich behandelt, der Aufrufer entscheidet,
    ob das ein Fehler ist)."""
    headers = _auth_header()
    if headers is None or not hostname:
        return None
    base = _base_url()
    try:
        r = httpx.get(
            f"{base}/api2/json/cluster/resources",
            params={"type": "vm"},
            headers=headers,
            timeout=_TIMEOUT,
            verify=_SSL_CONTEXT,
        )
        r.raise_for_status()
        entries = r.json().get("data", [])
    except (httpx.HTTPError, ValueError):
        return None
    for e in entries:
        if e.get("type") == "lxc" and e.get("name") == hostname:
            return {"vmid": e["vmid"], "node": e["node"]}
    return None


def _wait_for_task(base: str, node: str, upid: str, headers: dict) -> tuple[bool, str]:
    deadline = time.monotonic() + _SNAPSHOT_MAX_WAIT_S
    while time.monotonic() < deadline:
        try:
            r = httpx.get(
                f"{base}/api2/json/nodes/{node}/tasks/{upid}/status",
                headers=headers,
                timeout=_TIMEOUT,
                verify=_SSL_CONTEXT,
            )
            r.raise_for_status()
            data = r.json()["data"]
        except (httpx.HTTPError, ValueError, KeyError) as e:
            return False, f"Status-Abfrage fehlgeschlagen: {e}"
        if data.get("status") != "running":
            if data.get("exitstatus") == "OK":
                return True, ""
            return False, f"Snapshot-Task fehlgeschlagen: {data.get('exitstatus')}"
        time.sleep(_SNAPSHOT_POLL_INTERVAL_S)
    return False, "Zeitüberschreitung beim Warten auf den Snapshot-Task"


def create_snapshot(node: str, vmid: int, snapname: str) -> tuple[bool, str]:
    """Erstellt einen LXC-Snapshot und wartet (bis zu _SNAPSHOT_MAX_WAIT_S)
    auf den Abschluss des asynchronen Proxmox-Tasks -- Proxmox-API-Aufrufe,
    die den Zustand aendern, liefern sofort eine Task-ID (UPID) zurueck,
    der eigentliche Snapshot laeuft im Hintergrund weiter. Ohne dieses
    Warten koennte 'Update anstoßen' loslaufen, bevor der Snapshot
    tatsaechlich fertig (oder ueberhaupt erfolgreich) ist -- genau das,
    wovor der Snapshot eigentlich schuetzen soll."""
    headers = _auth_header()
    if headers is None:
        return False, "Proxmox ist nicht konfiguriert (URL/Token fehlt)"
    base = _base_url()
    try:
        r = httpx.post(
            f"{base}/api2/json/nodes/{node}/lxc/{vmid}/snapshot",
            data={"snapname": snapname},
            headers=headers,
            timeout=_TIMEOUT,
            verify=_SSL_CONTEXT,
        )
        r.raise_for_status()
        upid = r.json()["data"]
    except (httpx.HTTPError, ValueError, KeyError) as e:
        return False, str(e)

    return _wait_for_task(base, node, upid, headers)

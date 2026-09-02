# astrapi_admin/modules/hosts/ui/user_inventory.py
"""Read-only Bestandsaufnahme-Dialog fuer die auf einem Host gefundenen
Nutzerkonten (E-012) -- rein informativ, siehe
user_policies/engine.py::resolve_users_for_host() fuer die eigentliche
Durchsetzung.

Anzeigefilter (Nutzerfeedback nach T-300-ADMIN): der Agent liefert
IMMER die vollstaendige Bestandsaufnahme (kein UID-Filter mehr, siehe
users.py -- es gibt keine saubere numerische Trennlinie zwischen
"System-" und "interessantem" Account). Welche Konten standardmaessig
ausgeblendet werden, ist stattdessen eine reine ANZEIGE-Einstellung
(hosts.hidden_system_usernames, Einstellungen > Nutzer-Anzeige) --
aendert nichts an den gespeicherten Daten, "Alle anzeigen" im Dialog
blendet jederzeit alles wieder ein."""
import fnmatch
import json

from astrapi_core.ui.render import render
from fastapi import Request
from fastapi.responses import HTMLResponse

from astrapi_admin.modules.hosts.ui.crud import KEY, router, store

# Muss mit config/settings.yaml::hidden_system_usernames.default in Sync
# bleiben -- das YAML-default befuellt nur das Formular beim ERSTEN
# Aufruf der Einstellungsseite, dieser Python-Default gilt, solange
# ueberhaupt noch nichts gespeichert wurde.
DEFAULT_HIDDEN_PATTERNS = [
    "daemon", "bin", "sys", "sync", "games", "man", "lp", "mail", "news",
    "uucp", "proxy", "www-data", "backup", "list", "irc", "_apt", "nobody",
    "messagebus", "sshd", "systemd-*",
]


def _hidden_patterns() -> list[str]:
    from astrapi_core.ui.settings_registry import get_module

    patterns = get_module("hosts", "hidden_system_usernames", DEFAULT_HIDDEN_PATTERNS)
    return patterns if isinstance(patterns, list) else DEFAULT_HIDDEN_PATTERNS


def _is_hidden(username: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(username, p) for p in patterns)


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

    patterns = _hidden_patterns()
    for u in inventory:
        u["hidden_by_filter"] = _is_hidden(u.get("username", ""), patterns)
    hidden_count = sum(1 for u in inventory if u["hidden_by_filter"])
    # Sichtbare Zeilen zuerst, ausgeblendete danach: die ausgeblendeten
    # Zeilen bleiben im DOM (nur per Alpine x-show/display:none versteckt,
    # fuer den "Alle anzeigen"-Umschalter), zaehlen also weiterhin fuer
    # CSS :nth-child mit. Ohne diese Gruppierung haengt die Zebra-Faerbung
    # der sichtbaren Zeilen vom Zufall ab, wie viele ausgeblendete Zeilen
    # in der urspruenglichen /etc/passwd-Reihenfolge dazwischenliegen.
    inventory.sort(key=lambda u: u["hidden_by_filter"])

    return render(
        request,
        "hosts/dialogs/user_inventory/modal.html",
        dict(
            description=description,
            inventory=inventory,
            checked_at=host.get("user_inventory_checked_at") or "",
            hidden_count=hidden_count,
        ),
    )

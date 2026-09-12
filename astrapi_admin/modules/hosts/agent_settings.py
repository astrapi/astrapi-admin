# astrapi_admin/modules/hosts/agent_settings.py
"""Server-seitig einstellbares Agent-Poll-Intervall (E-011) + Zeitzone
(T-321-ADMIN).

astrapi-admin-agent ist rein pull-basiert -- kein Push/SSH-Kanal zum
Agenten. Statt einer direkten Fernsteuerung liest der Agent bei jedem
ohnehin stattfindenden Poll (GET /api/agent/policy) das gewuenschte
Intervall aus und passt bei Abweichung SEINEN EIGENEN systemd-Timer per
Drop-in-Override an (astrapi_admin_agent.timer_config). Wirkt deshalb
erst beim naechsten Poll-Zyklus, nicht sofort. Dieselbe Grundidee traegt
die Zeitzone: ein einziges globales Setting statt eines Policy-Felds,
weil alle Hosts dieselbe Zeiteinteilung bekommen sollen
(Nutzerentscheidung T-321-ADMIN) -- kein per-Host/Gruppen-Feld noetig.
"""


def poll_interval_minutes() -> int:
    """Liest agent_poll_interval_minutes robust aus dem Settings-Store.

    settings_save_module() (astrapi_core) speichert type: number-Felder
    als rohen Formular-String, kein automatisches int() -- muss hier
    defensiv geparst werden. Clamp auf [1, 1440] schuetzt gegen einen
    versehentlichen Extremwert (z.B. "0" -> Dauerpolling).
    """
    from astrapi_core.ui.settings_registry import get_module

    raw = get_module("hosts", "agent_poll_interval_minutes", 15)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 15
    return max(1, min(1440, value))


def timezone() -> str:
    """Liest agent_timezone aus dem Settings-Store.

    Default bewusst leer ("nicht verwaltet") statt eines festen Werts
    wie "Europe/Berlin" -- sonst wuerde das Ausrollen dieses Features
    allein schon auf jedem bestehenden Host unangekuendigt die Zeitzone
    aendern. Der Agent laesst die Zeitzone unangetastet, solange dieses
    Setting leer ist (siehe api/agent.py::get_policy(), das Feld fehlt
    dann ganz in der Policy-Antwort)."""
    from astrapi_core.ui.settings_registry import get_module

    return (get_module("hosts", "agent_timezone", "") or "").strip()

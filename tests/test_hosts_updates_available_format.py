"""hosts/ui/crud.py::_format_updates_available() -- Freigabestatus war in
der Host-Liste nicht sichtbar: nach "Update anstoßen" stand dort weiter nur
die zuletzt gemeldete Update-Anzahl, ohne Hinweis, dass eine Freigabe schon
erfolgt ist und der Agent nur noch den naechsten Poll-Zyklus braucht."""
from astrapi_admin.modules.hosts.ui.crud import (
    _format_os_type,
    _format_updates_available,
    _updates_category,
)


def test_kein_pending_action_zeigt_normale_anzeige():
    assert _format_updates_available(3, None, None) == "3 Updates"


def test_pending_action_update_haengt_hinweis_an():
    assert _format_updates_available(3, None, "update") == "3 Updates -- angefordert, wartet auf Agent"


def test_pending_action_update_auch_bei_aktuell():
    assert _format_updates_available(0, None, "update") == "aktuell -- angefordert, wartet auf Agent"


def test_pending_action_update_auch_bei_noch_nicht_geprueft():
    assert _format_updates_available(-1, None, "update") == "noch nicht geprüft -- angefordert, wartet auf Agent"


def test_leerer_pending_action_zeigt_keinen_hinweis():
    assert _format_updates_available(0, None, "") == "aktuell"


def test_updates_category_unbekannt_hat_keinen_punkt():
    """Nutzerwunsch 2026-09-04: Farbpunkt vor dem Updates-Text -- ein
    gruener Punkt fuer 'noch nie geprueft' waere falsch beruhigend."""
    assert _updates_category(None) == ""
    assert _updates_category(-1) == ""


def test_updates_category_keine_updates_ist_gruen():
    assert _updates_category(0) == "ok"


def test_updates_category_normale_updates_ist_orange():
    assert _updates_category(3, security_value=0) == "warning"
    assert _updates_category(3, security_value=None) == "warning"


def test_updates_category_sicherheitsupdates_ist_rot():
    assert _updates_category(3, security_value=1) == "error"


def test_format_os_type_zeigt_lesbare_namen():
    assert _format_os_type("archlinux") == "Arch"
    assert _format_os_type("debian") == "Debian"


def test_format_os_type_unbekannter_wert_faellt_auf_rohwert_zurueck():
    assert _format_os_type("windows") == "windows"
    assert _format_os_type(None) == "—"
    assert _format_os_type("") == "—"


def test_next_run_at_liest_aus_last_report_details():
    import json

    from astrapi_admin.modules.hosts.ui.crud import _next_run_at

    last_report = json.dumps({"status": "ok", "summary": "x", "details": {"next_run_at": "2026-09-04 22:00:00"}})
    assert _next_run_at(last_report) == "2026-09-04 22:00:00"


def test_next_run_at_ohne_last_report_ist_unbekannt():
    from astrapi_admin.modules.hosts.ui.crud import _next_run_at

    assert _next_run_at(None) == "unbekannt"
    assert _next_run_at("") == "unbekannt"


def test_next_run_at_aelterer_agent_ohne_feld_ist_unbekannt():
    import json

    from astrapi_admin.modules.hosts.ui.crud import _next_run_at

    last_report = json.dumps({"status": "ok", "summary": "x", "details": {}})
    assert _next_run_at(last_report) == "unbekannt"


def test_next_run_at_kaputtes_json_ist_unbekannt():
    from astrapi_admin.modules.hosts.ui.crud import _next_run_at

    assert _next_run_at("kein json") == "unbekannt"

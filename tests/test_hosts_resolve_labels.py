"""hosts/ui/crud.py::_resolve_labels() -- T-285-ADMIN: setzt 'description'
aus dem Hostnamen, damit die generische NAME-Spalte der Listenansicht
(list_wrapper_inner.html: item_data.description or .job or .host or
item_name) den Hostnamen statt der rohen DB-ID zeigt. Kein separates
'Anzeigename'-Feld mehr (Nutzerwunsch: "der Hostname reicht mir")."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts.ui.crud import _display_status, _resolve_labels


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def test_resolve_labels_setzt_description_aus_hostname():
    item = {"hostname": "lxc01", "group_ids": [], "policy_ids": []}
    result = _resolve_labels("4", item)
    assert result["description"] == "lxc01"


def test_resolve_labels_faellt_auf_item_id_zurueck_ohne_hostname():
    item = {"hostname": "", "group_ids": [], "policy_ids": []}
    result = _resolve_labels("4", item)
    assert result["description"] == "4"


def test_resolve_labels_bildet_drift_auf_warning_ab():
    """Nutzerentscheidung 2026-09-04: die generische Status-Spalte kennt
    nur ok/error/warning/running/pending/neu -- drift/conflict werden fuer
    die Anzeige auf 'warning' abgebildet (Details weiterhin ueber "Log
    anzeigen" einsehbar)."""
    item = {"hostname": "lxc01", "group_ids": [], "policy_ids": [], "last_status": "drift"}
    result = _resolve_labels("4", item)
    assert result["last_status"] == "warning"


def test_resolve_labels_bildet_conflict_auf_warning_ab():
    item = {"hostname": "lxc01", "group_ids": [], "policy_ids": [], "last_status": "conflict"}
    result = _resolve_labels("4", item)
    assert result["last_status"] == "warning"


def test_resolve_labels_laesst_ok_und_error_unveraendert():
    for status in ("ok", "error", "", None):
        item = {"hostname": "lxc01", "group_ids": [], "policy_ids": [], "last_status": status}
        result = _resolve_labels("4", item)
        assert result["last_status"] == status


def test_display_status_bildet_nur_drift_und_conflict_ab():
    assert _display_status("drift") == "warning"
    assert _display_status("conflict") == "warning"
    assert _display_status("ok") == "ok"
    assert _display_status("error") == "error"
    assert _display_status("") == ""
    assert _display_status(None) is None


def test_resolve_labels_setzt_updates_category_und_lesbaren_os_type():
    """Nutzerwunsch 2026-09-04: OS als reiner Text (kein Badge mehr),
    Updates-Spalte mit Farbpunkt statt Badge."""
    item = {
        "hostname": "lxc01",
        "group_ids": [],
        "policy_ids": [],
        "os_type": "debian",
        "updates_available": 2,
        "security_updates_available": 1,
    }
    result = _resolve_labels("4", item)
    assert result["os_type"] == "Debian"
    assert result["updates_category"] == "error"

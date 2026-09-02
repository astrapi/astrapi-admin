"""hosts/ui/crud.py::_resolve_labels() -- T-285-ADMIN: setzt 'description'
aus dem Hostnamen, damit die generische NAME-Spalte der Listenansicht
(list_wrapper_inner.html: item_data.description or .job or .host or
item_name) den Hostnamen statt der rohen DB-ID zeigt. Kein separates
'Anzeigename'-Feld mehr (Nutzerwunsch: "der Hostname reicht mir")."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts.ui.crud import _resolve_labels


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

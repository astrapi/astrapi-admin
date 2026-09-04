"""hosts/ui/updates.py::cancel_update_dialog()/cancel_update() -- Nutzer
soll ein per "Update anstoßen" gesetztes pending_action wieder zurücknehmen
können, solange der Agent es noch nicht abgeholt hat."""
from unittest.mock import patch

import pytest
from astrapi_core.system import db
from fastapi import HTTPException

from astrapi_admin.modules.hosts.ui import updates as hosts_updates
from astrapi_admin.modules.hosts.ui.crud import store as hosts_store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _create_host(**overrides) -> str:
    values = {
        "hostname": "lxc99",
        "label": "lxc99",
        "os_type": "debian",
        "group_ids": [], "policy_ids": [],
        "token_hash": "x",
        "last_seen": "", "last_report": "", "last_status": "",
        "pending_action": "",
        "proxmox_vmid": -1,
        "snapshot_before_update": True,
        "updates_package_list": [],
        "security_updates_package_list": [],
        "enabled": True,
    }
    values.update(overrides)
    return str(hosts_store.create(None, values))


def test_cancel_update_setzt_pending_action_zurueck():
    host_id = _create_host(pending_action="update")

    hosts_updates.cancel_update(host_id)

    assert hosts_store.get(host_id)["pending_action"] == ""


def test_cancel_update_ohne_ausstehendes_update_ist_ein_no_op():
    """Spaeter Klick, nachdem der Agent das Update bereits abgeholt und
    pending_action selbst schon zurueckgesetzt hat -- darf nichts anderes
    ueberschreiben (z.B. ein zwischenzeitlich neu gesetztes pending_action)."""
    host_id = _create_host(pending_action="")

    hosts_updates.cancel_update(host_id)

    assert hosts_store.get(host_id)["pending_action"] == ""


def test_cancel_update_unbekannter_host_liefert_404():
    with pytest.raises(HTTPException) as exc_info:
        hosts_updates.cancel_update("does-not-exist")

    assert exc_info.value.status_code == 404


def test_cancel_update_dialog_zeigt_hostnamen():
    host_id = _create_host()

    with patch("astrapi_admin.modules.hosts.ui.updates.render") as mock_render:
        hosts_updates.cancel_update_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert "lxc99" in ctx["description"]
    assert ctx["confirm_url"] == f"/api/hosts/{host_id}/cancel-update"
    assert ctx["method"] == "patch"

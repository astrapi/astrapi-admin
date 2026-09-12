"""hosts/ui/trigger.py -- T-322-ADMIN: "Jetzt pollen" verbindet sich nur
zum Trigger-Port des Agenten (astrapi-admin-agent-trigger.socket auf dem
Host), ohne Authentifizierung (Nutzerentscheidung: host_token kann dafuer
nicht wiederverwendet werden, siehe Modul-Docstring)."""
from unittest.mock import patch

import pytest
from astrapi_core.system import db
from fastapi import HTTPException

from astrapi_admin.modules.hosts.ui import trigger as hosts_trigger
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
        "enabled": True,
    }
    values.update(overrides)
    return str(hosts_store.create(None, values))


def test_trigger_poll_dialog_host_nicht_gefunden():
    resp = hosts_trigger.trigger_poll_dialog("999", request=None)
    assert resp.status_code == 404


def test_trigger_poll_dialog_zeigt_label():
    host_id = _create_host(label="mein-host")

    with patch("astrapi_admin.modules.hosts.ui.trigger.render") as mock_render:
        hosts_trigger.trigger_poll_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert "mein-host" in ctx["description"]
    assert ctx["confirm_url"] == f"/api/hosts/{host_id}/trigger-poll"


def test_trigger_poll_host_nicht_gefunden():
    with pytest.raises(HTTPException) as exc:
        hosts_trigger.trigger_poll("999")
    assert exc.value.status_code == 404


def test_trigger_poll_verbindet_sich_zum_richtigen_host_und_port():
    host_id = _create_host(hostname="lxc99.simpsons.lan")

    with patch("astrapi_admin.modules.hosts.ui.trigger.socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__ = lambda self: self
        mock_conn.return_value.__exit__ = lambda self, *a: None
        hosts_trigger.trigger_poll(host_id)

    mock_conn.assert_called_once_with(("lxc99.simpsons.lan", 8765), timeout=5)


def test_trigger_poll_wirft_502_bei_verbindungsfehler():
    host_id = _create_host(hostname="lxc99.simpsons.lan")

    with patch(
        "astrapi_admin.modules.hosts.ui.trigger.socket.create_connection",
        side_effect=OSError("Connection refused"),
    ):
        with pytest.raises(HTTPException) as exc:
            hosts_trigger.trigger_poll(host_id)

    assert exc.value.status_code == 502

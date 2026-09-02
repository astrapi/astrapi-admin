"""hosts/ui/user_inventory.py -- E-012: read-only Bestandsaufnahme-Dialog,
rein informativ (macht nie einen Account "verwaltet"). Muster wie
test_trigger_update_dialog.py: render() gemockt, ctx geprüft."""
import json
from unittest.mock import patch

import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts.ui import user_inventory as hosts_user_inventory
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
        "group_ids": [],
        "policy_ids": [],
        "user_policy_ids": [],
        "mirror_repos": [],
        "token_hash": "x",
        "last_seen": "",
        "last_report": "",
        "last_status": "",
        "pending_action": "",
        "updates_available": -1,
        "updates_checked_at": "",
        "user_inventory": "",
        "user_inventory_checked_at": "",
        "enabled": True,
    }
    values.update(overrides)
    return str(hosts_store.create(None, values))


def test_user_inventory_dialog_parst_gespeicherte_bestandsaufnahme():
    inventory = [{"username": "alice", "uid": 1500, "shell": "/bin/bash", "sudo": True, "has_ssh_keys": True, "managed": True}]
    host_id = _create_host(user_inventory=json.dumps(inventory), user_inventory_checked_at="2026-09-02 18:00:00")

    with patch("astrapi_admin.modules.hosts.ui.user_inventory.render") as mock_render:
        hosts_user_inventory.user_inventory_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["inventory"] == inventory
    assert ctx["checked_at"] == "2026-09-02 18:00:00"


def test_user_inventory_dialog_ohne_bestandsaufnahme_liefert_leere_liste():
    host_id = _create_host()

    with patch("astrapi_admin.modules.hosts.ui.user_inventory.render") as mock_render:
        hosts_user_inventory.user_inventory_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["inventory"] == []


def test_user_inventory_dialog_zeigt_label_oder_hostname_als_beschreibung():
    host_id = _create_host(label="", hostname="lxc42")

    with patch("astrapi_admin.modules.hosts.ui.user_inventory.render") as mock_render:
        hosts_user_inventory.user_inventory_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["description"] == "lxc42"


def test_user_inventory_dialog_unbekannter_host_gibt_404():
    response = hosts_user_inventory.user_inventory_dialog("nie-angelegt", request=None)

    assert response.status_code == 404

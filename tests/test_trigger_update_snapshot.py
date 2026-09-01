"""hosts/ui/updates.py::trigger_update() -- optionaler Proxmox-Snapshot
vor dem Setzen von pending_action (E-009). Schlaegt der Snapshot fehl
(nur wenn snapshot_before_update an UND ein Proxmox-LXC erkannt wurde),
wird pending_action NICHT gesetzt -- sonst waere die Sicherheitsfunktion
wirkungslos."""
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
        "enabled": True,
    }
    values.update(overrides)
    return str(hosts_store.create(None, values))


def test_ohne_proxmox_vmid_kein_snapshot_versuch():
    host_id = _create_host(proxmox_vmid=-1)

    with patch("astrapi_admin.modules.hosts.proxmox_client.find_lxc_by_hostname") as mock_find:
        hosts_updates.trigger_update(host_id)

    mock_find.assert_not_called()
    assert hosts_store.get(host_id)["pending_action"] == "update"


def test_mit_deaktiviertem_toggle_kein_snapshot_versuch():
    host_id = _create_host(proxmox_vmid=105, snapshot_before_update=False)

    with patch("astrapi_admin.modules.hosts.proxmox_client.find_lxc_by_hostname") as mock_find:
        hosts_updates.trigger_update(host_id)

    mock_find.assert_not_called()
    assert hosts_store.get(host_id)["pending_action"] == "update"


def test_erfolgreicher_snapshot_setzt_pending_action():
    host_id = _create_host(proxmox_vmid=105, snapshot_before_update=True)

    with patch(
        "astrapi_admin.modules.hosts.proxmox_client.find_lxc_by_hostname",
        return_value={"vmid": 105, "node": "pve2"},
    ), patch(
        "astrapi_admin.modules.hosts.proxmox_client.create_snapshot",
        return_value=(True, ""),
    ) as mock_snap:
        hosts_updates.trigger_update(host_id)

    mock_snap.assert_called_once()
    assert mock_snap.call_args[0][0] == "pve2"
    assert mock_snap.call_args[0][1] == 105
    assert hosts_store.get(host_id)["pending_action"] == "update"


def test_fehlgeschlagener_snapshot_blockiert_das_update():
    host_id = _create_host(proxmox_vmid=105, snapshot_before_update=True)

    with patch(
        "astrapi_admin.modules.hosts.proxmox_client.find_lxc_by_hostname",
        return_value={"vmid": 105, "node": "pve2"},
    ), patch(
        "astrapi_admin.modules.hosts.proxmox_client.create_snapshot",
        return_value=(False, "storage does not support snapshots"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            hosts_updates.trigger_update(host_id)

    assert exc_info.value.status_code == 502
    assert hosts_store.get(host_id)["pending_action"] == ""


def test_lxc_nicht_mehr_gefunden_blockiert_das_update():
    host_id = _create_host(proxmox_vmid=105, snapshot_before_update=True)

    with patch("astrapi_admin.modules.hosts.proxmox_client.find_lxc_by_hostname", return_value=None):
        with pytest.raises(HTTPException):
            hosts_updates.trigger_update(host_id)

    assert hosts_store.get(host_id)["pending_action"] == ""


def test_host_nicht_gefunden_wirft_404():
    with pytest.raises(HTTPException) as exc_info:
        hosts_updates.trigger_update("nicht-vorhanden")

    assert exc_info.value.status_code == 404

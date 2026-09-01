"""hosts/ui/updates.py::_describe_pending_packages()/trigger_update_dialog()
-- T-284-ADMIN: vor der Freigabe zeigen, welche Pakete ein Update
betreffen wuerde, nicht nur die Anzahl."""
from unittest.mock import patch

import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts.ui import updates as hosts_updates
from astrapi_admin.modules.hosts.ui.crud import store as hosts_store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def test_describe_pending_packages_ohne_bekannte_updates():
    assert "Keine bekannten ausstehenden Updates" in hosts_updates._describe_pending_packages({})


def test_describe_pending_packages_markiert_security_pakete():
    host = {
        "updates_package_list": ["htop", "libssl3"],
        "security_updates_package_list": ["libssl3"],
    }
    text = hosts_updates._describe_pending_packages(host)
    assert "2 Updates betroffen" in text
    assert "htop" in text
    assert "libssl3 (sicherheitsrelevant)" in text


def test_describe_pending_packages_kappt_lange_listen():
    host = {"updates_package_list": [f"pkg{i}" for i in range(15)], "security_updates_package_list": []}
    text = hosts_updates._describe_pending_packages(host)
    assert "15 Updates betroffen" in text
    assert "und 5 weitere" in text
    assert "pkg9" in text
    assert "pkg14" not in text


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


def test_trigger_update_dialog_zeigt_paketliste_in_der_beschreibung():
    host_id = _create_host(updates_package_list=["caddy", "tzdata"], security_updates_package_list=[])

    with patch("astrapi_admin.modules.hosts.ui.updates.render") as mock_render:
        hosts_updates.trigger_update_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert "caddy" in ctx["description"]
    assert "tzdata" in ctx["description"]
    assert "2 Updates betroffen" in ctx["description"]

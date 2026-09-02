"""hosts/ui/updates.py::_pending_packages_list()/trigger_update_dialog()
-- T-284-ADMIN: vor der Freigabe zeigen, welche Pakete ein Update
betreffen wuerde, als scrollbare Liste (nicht im Fliesstext) und ohne
den unnoetigen "wie wird aktualisiert"-Hinweis (Nutzer-Feedback
2026-09-02: "die gefundenen Updates sollten in einer scrollbaren Liste
stehen, und der Hinweis wie ich updaten kann ist unnötig")."""
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


def test_pending_packages_list_ohne_bekannte_updates():
    items_list, items_label = hosts_updates._pending_packages_list({})
    assert items_list is None
    assert items_label is None


def test_pending_packages_list_markiert_security_pakete():
    host = {
        "updates_package_list": ["htop", "libssl3"],
        "security_updates_package_list": ["libssl3"],
    }
    items_list, items_label = hosts_updates._pending_packages_list(host)
    assert items_list == ["htop", "libssl3 (sicherheitsrelevant)"]
    assert items_label == "2 Updates betroffen:"


def test_pending_packages_list_enthaelt_alle_eintraege_ohne_kappung():
    """Die Liste ist jetzt scrollbar -- keine Kappung mehr noetig."""
    host = {"updates_package_list": [f"pkg{i}" for i in range(15)], "security_updates_package_list": []}
    items_list, items_label = hosts_updates._pending_packages_list(host)
    assert len(items_list) == 15
    assert "pkg14" in items_list
    assert items_label == "15 Updates betroffen:"


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


def test_trigger_update_dialog_uebergibt_paketliste_separat():
    host_id = _create_host(updates_package_list=["caddy", "tzdata"], security_updates_package_list=[])

    with patch("astrapi_admin.modules.hosts.ui.updates.render") as mock_render:
        hosts_updates.trigger_update_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["items_list"] == ["caddy", "tzdata"]
    assert ctx["items_label"] == "2 Updates betroffen:"


def test_trigger_update_dialog_beschreibung_enthaelt_keinen_wie_hinweis():
    host_id = _create_host(updates_package_list=["caddy"], security_updates_package_list=[])

    with patch("astrapi_admin.modules.hosts.ui.updates.render") as mock_render:
        hosts_updates.trigger_update_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert "apt upgrade" not in ctx["description"]
    assert "pacman" not in ctx["description"]
    assert ctx["description"] == "lxc99"


def test_trigger_update_dialog_ohne_bekannte_updates_zeigt_hinweis_in_beschreibung():
    host_id = _create_host()

    with patch("astrapi_admin.modules.hosts.ui.updates.render") as mock_render:
        hosts_updates.trigger_update_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["items_list"] is None
    assert "keine bekannten ausstehenden Updates" in ctx["description"]


def test_trigger_update_dialog_snapshot_hinweis_bleibt_erhalten():
    host_id = _create_host(proxmox_vmid=105, snapshot_before_update=True)

    with patch("astrapi_admin.modules.hosts.ui.updates.render") as mock_render:
        hosts_updates.trigger_update_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert "Proxmox-Snapshot" in ctx["description"]

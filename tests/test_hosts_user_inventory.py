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
    assert ctx["inventory"][0]["username"] == "alice"
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


# ── Anzeigefilter (Nutzerfeedback nach T-300-ADMIN) ────────────────────


def test_is_hidden_erkennt_exakten_namen():
    assert hosts_user_inventory._is_hidden("sshd", ["sshd"]) is True
    assert hosts_user_inventory._is_hidden("caddy", ["sshd"]) is False


def test_is_hidden_unterstuetzt_glob_muster():
    assert hosts_user_inventory._is_hidden("systemd-network", ["systemd-*"]) is True
    assert hosts_user_inventory._is_hidden("systemd-resolve", ["systemd-*"]) is True
    assert hosts_user_inventory._is_hidden("claude", ["systemd-*"]) is False


def test_user_inventory_dialog_markiert_default_systemkonten_als_ausgeblendet():
    """Ohne gesetztes Setting greift der Python-seitige Default -- muss
    dieselben interessanten Service-Accounts (caddy, claude) wie das
    urspruengliche Nutzerbeispiel sichtbar lassen, aber sshd ausblenden."""
    inventory = [
        {"username": "claude", "uid": 997, "shell": "/bin/bash"},
        {"username": "caddy", "uid": 999, "shell": "/usr/sbin/nologin"},
        {"username": "sshd", "uid": 101, "shell": "/usr/sbin/nologin"},
        {"username": "systemd-network", "uid": 998, "shell": "/usr/sbin/nologin"},
    ]
    host_id = _create_host(user_inventory=json.dumps(inventory))

    with patch("astrapi_admin.modules.hosts.ui.user_inventory.render") as mock_render:
        hosts_user_inventory.user_inventory_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    hidden = {u["username"]: u["hidden_by_filter"] for u in ctx["inventory"]}
    assert hidden == {"claude": False, "caddy": False, "sshd": True, "systemd-network": True}
    assert ctx["hidden_count"] == 2


def test_user_inventory_dialog_respektiert_gesetztes_setting(monkeypatch):
    from astrapi_core.ui import settings_registry

    monkeypatch.setattr(
        settings_registry, "get_module", lambda module_key, key, default=None: ["caddy"]
    )
    inventory = [{"username": "caddy", "uid": 999, "shell": "x"}, {"username": "claude", "uid": 997, "shell": "x"}]
    host_id = _create_host(user_inventory=json.dumps(inventory))

    with patch("astrapi_admin.modules.hosts.ui.user_inventory.render") as mock_render:
        hosts_user_inventory.user_inventory_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    hidden = {u["username"]: u["hidden_by_filter"] for u in ctx["inventory"]}
    assert hidden == {"caddy": True, "claude": False}


def test_user_inventory_dialog_leere_liste_setting_zeigt_alles():
    from astrapi_core.ui import settings_registry

    with patch.object(settings_registry, "get_module", return_value=[]):
        inventory = [{"username": "sshd", "uid": 101, "shell": "x"}]
        host_id = _create_host(user_inventory=json.dumps(inventory))

        with patch("astrapi_admin.modules.hosts.ui.user_inventory.render") as mock_render:
            hosts_user_inventory.user_inventory_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["inventory"][0]["hidden_by_filter"] is False
    assert ctx["hidden_count"] == 0


def test_user_inventory_dialog_gruppiert_sichtbare_zeilen_vor_ausgeblendeten():
    """Ausgeblendete Zeilen bleiben per Alpine x-show im DOM (nur
    display:none), zaehlen also weiterhin fuer CSS :nth-child mit --
    ohne diese Gruppierung haengt die Zebra-Faerbung der sichtbaren
    Zeilen vom Zufall ab, wie viele ausgeblendete Zeilen in der
    urspruenglichen /etc/passwd-Reihenfolge dazwischenliegen (am echten
    Screenshot beobachtet: root/ottoadm/caddy/test gleich gefaerbt,
    nur claude abweichend -- weil dazwischen unterschiedlich viele
    ausgeblendete Systemkonten lagen)."""
    inventory = [
        {"username": "root"},       # sichtbar
        {"username": "daemon"},     # ausgeblendet (Default-Muster)
        {"username": "bin"},        # ausgeblendet
        {"username": "caddy"},      # sichtbar
        {"username": "sshd"},       # ausgeblendet
        {"username": "claude"},     # sichtbar
    ]
    host_id = _create_host(user_inventory=json.dumps(inventory))

    with patch("astrapi_admin.modules.hosts.ui.user_inventory.render") as mock_render:
        hosts_user_inventory.user_inventory_dialog(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    order = [u["username"] for u in ctx["inventory"]]
    assert order == ["root", "caddy", "claude", "daemon", "bin", "sshd"]

"""proxmox_client.py: HTTP-Client gegen die Proxmox-API (E-009) --
fehlertolerant wie mirror_client.py (None statt Exception), Konfiguration
kommt aus Modul-Settings + einem 'type: password'-Secret."""
import httpx
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts import proxmox_client


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    from astrapi_core.system import secrets

    secrets._key_path_prod = None
    secrets._key_path_dev = None
    secrets.configure(key_path=tmp_path / ".secret.key")
    yield


def _configure(base_url="https://pve.simpsons.lan:8006", token_id="root@pam!astrapi-admin", token_secret="s3cr3t"):
    from astrapi_core.system.secrets import set_secret
    from astrapi_core.ui.settings_registry import set_module

    set_module("hosts", "proxmox_base_url", base_url)
    set_module("hosts", "proxmox_token_id", token_id)
    if token_secret:
        set_secret("module.hosts.proxmox_token_secret", token_secret)


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


def test_configured_false_ohne_einstellungen():
    assert proxmox_client.configured() is False


def test_configured_true_wenn_alles_gesetzt():
    _configure()
    assert proxmox_client.configured() is True


def test_find_lxc_by_hostname_ohne_konfiguration_liefert_none():
    assert proxmox_client.find_lxc_by_hostname("lxc01") is None


def test_find_lxc_by_hostname_findet_passenden_lxc(monkeypatch):
    _configure()
    payload = {
        "data": [
            {"type": "qemu", "name": "lxc01", "vmid": 999, "node": "pve1"},
            {"type": "lxc", "name": "lxc01", "vmid": 105, "node": "pve2"},
            {"type": "lxc", "name": "lxc02", "vmid": 106, "node": "pve1"},
        ]
    }

    def _fake_get(url, **kw):
        assert kw["headers"]["Authorization"] == "PVEAPIToken=root@pam!astrapi-admin=s3cr3t"
        return _FakeResponse(json_data=payload)

    monkeypatch.setattr(proxmox_client.httpx, "get", _fake_get)

    result = proxmox_client.find_lxc_by_hostname("lxc01")

    assert result == {"vmid": 105, "node": "pve2"}


def test_find_lxc_by_hostname_kein_treffer_liefert_none(monkeypatch):
    _configure()
    monkeypatch.setattr(
        proxmox_client.httpx, "get",
        lambda url, **kw: _FakeResponse(json_data={"data": [{"type": "lxc", "name": "anderer", "vmid": 1, "node": "pve1"}]}),
    )

    assert proxmox_client.find_lxc_by_hostname("lxc01") is None


def test_find_lxc_by_hostname_bei_netzwerkfehler_liefert_none(monkeypatch):
    _configure()

    def _raise(url, **kw):
        raise httpx.ConnectError("kein Netz")

    monkeypatch.setattr(proxmox_client.httpx, "get", _raise)

    assert proxmox_client.find_lxc_by_hostname("lxc01") is None


def test_create_snapshot_ohne_konfiguration_liefert_fehler():
    ok, detail = proxmox_client.create_snapshot("pve1", 105, "snap1")
    assert ok is False
    assert "nicht konfiguriert" in detail


def test_create_snapshot_wartet_auf_taskabschluss_und_liefert_ok(monkeypatch):
    _configure()
    calls = []

    def _fake_post(url, **kw):
        calls.append(("post", url))
        return _FakeResponse(json_data={"data": "UPID:pve2:snap-task"})

    def _fake_get(url, **kw):
        calls.append(("get", url))
        return _FakeResponse(json_data={"data": {"status": "stopped", "exitstatus": "OK"}})

    monkeypatch.setattr(proxmox_client.httpx, "post", _fake_post)
    monkeypatch.setattr(proxmox_client.httpx, "get", _fake_get)
    monkeypatch.setattr(proxmox_client.time, "sleep", lambda s: None)

    ok, detail = proxmox_client.create_snapshot("pve2", 105, "snap1")

    assert ok is True
    assert detail == ""
    assert calls[0] == ("post", "https://pve.simpsons.lan:8006/api2/json/nodes/pve2/lxc/105/snapshot")
    assert calls[1] == ("get", "https://pve.simpsons.lan:8006/api2/json/nodes/pve2/tasks/UPID:pve2:snap-task/status")


def test_create_snapshot_meldet_fehlgeschlagenen_task(monkeypatch):
    _configure()
    monkeypatch.setattr(
        proxmox_client.httpx, "post",
        lambda url, **kw: _FakeResponse(json_data={"data": "UPID:pve2:snap-task"}),
    )
    monkeypatch.setattr(
        proxmox_client.httpx, "get",
        lambda url, **kw: _FakeResponse(json_data={"data": {"status": "stopped", "exitstatus": "storage does not support snapshots"}}),
    )

    ok, detail = proxmox_client.create_snapshot("pve2", 105, "snap1")

    assert ok is False
    assert "storage does not support snapshots" in detail


def test_create_snapshot_bei_post_fehler_liefert_fehler(monkeypatch):
    _configure()

    def _raise(url, **kw):
        raise httpx.ConnectError("kein Netz")

    monkeypatch.setattr(proxmox_client.httpx, "post", _raise)

    ok, detail = proxmox_client.create_snapshot("pve2", 105, "snap1")

    assert ok is False
    assert detail

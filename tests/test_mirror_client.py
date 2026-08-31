"""mirror_client.py: HTTP-Client gegen astrapi-mirror -- fehlertolerant
(leere Liste/None statt Exception), Basis-URL kommt aus einer
Modul-Einstellung."""
import httpx
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts import mirror_client


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _set_base_url(url: str) -> None:
    from astrapi_core.ui.settings_registry import set_module

    set_module("hosts", "mirror_base_url", url)


class _FakeResponse:
    def __init__(self, json_data=None, text="", status_code=200):
        self._json = json_data
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


def test_list_debian_repos_ohne_konfigurierte_url_liefert_leere_liste():
    assert mirror_client.list_debian_repos() == []


def test_list_debian_repos_filtert_deaktivierte_und_liest_slug_label(monkeypatch):
    _set_base_url("https://mirror.simpsons.lan")
    payload = {
        "debian": {
            "9": {"slug": "caddy", "label": "caddy", "enabled": True},
            "2": {"slug": "jellyfin", "label": "Jellyfin", "enabled": True},
            "3": {"slug": "disabled-repo", "label": "Aus", "enabled": False},
        }
    }
    monkeypatch.setattr(mirror_client.httpx, "get", lambda url, **kw: _FakeResponse(json_data=payload))

    result = mirror_client.list_debian_repos()

    assert {"value": "caddy", "label": "caddy"} in result
    assert {"value": "jellyfin", "label": "Jellyfin"} in result
    assert not any(r["value"] == "disabled-repo" for r in result)


def test_list_debian_repos_bei_netzwerkfehler_liefert_leere_liste(monkeypatch):
    _set_base_url("https://mirror.simpsons.lan")

    def _raise(url, **kw):
        raise httpx.ConnectError("kein Netz")

    monkeypatch.setattr(mirror_client.httpx, "get", _raise)

    assert mirror_client.list_debian_repos() == []


def test_list_debian_repos_bei_kaputtem_json_liefert_leere_liste(monkeypatch):
    _set_base_url("https://mirror.simpsons.lan")

    class _BadJson(_FakeResponse):
        def json(self):
            raise ValueError("kein JSON")

    monkeypatch.setattr(mirror_client.httpx, "get", lambda url, **kw: _BadJson())

    assert mirror_client.list_debian_repos() == []


def test_fetch_sources_content_ohne_konfigurierte_url_liefert_none():
    assert mirror_client.fetch_sources_content("caddy") is None


def test_fetch_sources_content_liefert_text(monkeypatch):
    _set_base_url("https://mirror.simpsons.lan")
    monkeypatch.setattr(
        mirror_client.httpx, "get", lambda url, **kw: _FakeResponse(text="Types: deb\n")
    )

    assert mirror_client.fetch_sources_content("caddy") == "Types: deb\n"


def test_fetch_sources_content_bei_fehlendem_repo_liefert_none(monkeypatch):
    _set_base_url("https://mirror.simpsons.lan")
    monkeypatch.setattr(
        mirror_client.httpx, "get", lambda url, **kw: _FakeResponse(status_code=404)
    )

    assert mirror_client.fetch_sources_content("nicht-vorhanden") is None

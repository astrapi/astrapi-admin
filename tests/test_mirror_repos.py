"""mirror_repos.py::resolve_mirror_config_files() -- haengt fuer jeden
Slug in host['mirror_repos'] eine fertige .sources-Datei an. Ein
Fehlschlag fuer einen Slug blockiert nicht die uebrigen (landet als
Eintrag in conflicts[], nicht als Exception) -- reines Host-Attribut,
unabhaengig von der Policy-Aufloesung."""
from astrapi_admin.modules.hosts import mirror_repos


def _result(**overrides):
    base = {"config_files": [], "conflicts": [], "status": "ok"}
    base.update(overrides)
    return base


def test_resolve_mirror_config_files_haengt_config_file_an(monkeypatch):
    monkeypatch.setattr(mirror_repos.mirror_client, "fetch_sources_content", lambda slug: "Types: deb\n")
    host = {"os_type": "debian", "mirror_repos": ["caddy"]}
    result = _result()

    mirror_repos.resolve_mirror_config_files(host, result)

    assert result["config_files"] == [
        {
            "path": "/etc/apt/sources.list.d/caddy.sources",
            "action": "enforce",
            "content": "Types: deb\n",
            "mode": "0644",
            "owner": "root",
            "group": "root",
            "force": False,
        }
    ]
    assert result["conflicts"] == []
    assert result["status"] == "ok"


def test_resolve_mirror_config_files_fehlschlag_landet_in_conflicts(monkeypatch):
    monkeypatch.setattr(mirror_repos.mirror_client, "fetch_sources_content", lambda slug: None)
    host = {"os_type": "debian", "mirror_repos": ["geloescht"]}
    result = _result()

    mirror_repos.resolve_mirror_config_files(host, result)

    assert result["config_files"] == []
    assert result["conflicts"] == [{"type": "mirror_source", "slug": "geloescht"}]
    assert result["status"] == "conflict"


def test_resolve_mirror_config_files_ein_fehlschlag_blockiert_nicht_die_uebrigen(monkeypatch):
    def _fake(slug):
        return None if slug == "kaputt" else f"content-{slug}"

    monkeypatch.setattr(mirror_repos.mirror_client, "fetch_sources_content", _fake)
    host = {"os_type": "debian", "mirror_repos": ["kaputt", "caddy"]}
    result = _result()

    mirror_repos.resolve_mirror_config_files(host, result)

    assert len(result["config_files"]) == 1
    assert result["config_files"][0]["path"] == "/etc/apt/sources.list.d/caddy.sources"
    assert result["conflicts"] == [{"type": "mirror_source", "slug": "kaputt"}]


def test_resolve_mirror_config_files_arch_host_wird_uebersprungen(monkeypatch):
    called = []
    monkeypatch.setattr(
        mirror_repos.mirror_client,
        "fetch_sources_content",
        lambda slug: called.append(slug),
    )
    host = {"os_type": "archlinux", "mirror_repos": ["caddy"]}
    result = _result()

    mirror_repos.resolve_mirror_config_files(host, result)

    assert called == []
    assert result["config_files"] == []


def test_resolve_mirror_config_files_ohne_mirror_repos_tut_nichts():
    host = {"os_type": "debian", "mirror_repos": []}
    result = _result()

    mirror_repos.resolve_mirror_config_files(host, result)

    assert result == _result()

"""mirror_repos.py::resolve_mirror_config_files() -- haengt fuer jeden
Slug in host['mirror_repos'] eine fertige .sources-Datei an UND eine
'absent'-Config-Datei fuer jeden von astrapi-mirror bekannten, aber
NICHT (mehr) ausgewaehlten Slug -- sonst erfaehrt der Agent nie, dass
ein abgewaehltes Repo wieder entfernt werden soll (echter Bug, vom
Nutzer gemeldet: "das Entfernen der sources klappt nicht"). Ein
Fehlschlag fuer einen Slug blockiert nicht die uebrigen (landet als
Eintrag in conflicts[], nicht als Exception) -- reines Host-Attribut,
unabhaengig von der Policy-Aufloesung."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts import mirror_repos


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _result(**overrides):
    base = {"config_files": [], "conflicts": [], "status": "ok"}
    base.update(overrides)
    return base


def test_resolve_mirror_config_files_haengt_config_file_an(monkeypatch):
    monkeypatch.setattr(mirror_repos.mirror_client, "fetch_sources_content", lambda slug: "Types: deb\n")
    monkeypatch.setattr(mirror_repos.mirror_client, "list_debian_repos", lambda: [{"value": "caddy", "label": "caddy"}])
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
    monkeypatch.setattr(mirror_repos.mirror_client, "list_debian_repos", lambda: [])
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
    monkeypatch.setattr(mirror_repos.mirror_client, "list_debian_repos", lambda: [])
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


def test_resolve_mirror_config_files_ohne_mirror_repos_tut_nichts(monkeypatch):
    monkeypatch.setattr(mirror_repos.mirror_client, "list_debian_repos", lambda: [])
    host = {"os_type": "debian", "mirror_repos": []}
    result = _result()

    mirror_repos.resolve_mirror_config_files(host, result)

    assert result == _result()


def test_resolve_mirror_config_files_abgewaehltes_repo_wird_absent(monkeypatch):
    """Kernfall des gemeldeten Bugs: caddy war gewaehlt, ist jetzt aus
    host['mirror_repos'] entfernt -- muss als 'absent' auftauchen, sonst
    loescht der Agent die zuvor geschriebene .sources-Datei nie."""
    monkeypatch.setattr(mirror_repos.mirror_client, "fetch_sources_content", lambda slug: "unused")
    monkeypatch.setattr(
        mirror_repos.mirror_client,
        "list_debian_repos",
        lambda: [{"value": "caddy", "label": "caddy"}, {"value": "nginx", "label": "nginx"}],
    )
    host = {"os_type": "debian", "mirror_repos": []}
    result = _result()

    mirror_repos.resolve_mirror_config_files(host, result)

    paths = {cf["path"]: cf["action"] for cf in result["config_files"]}
    assert paths == {
        "/etc/apt/sources.list.d/caddy.sources": "absent",
        "/etc/apt/sources.list.d/nginx.sources": "absent",
    }


def test_resolve_mirror_config_files_ausgewaehltes_repo_nicht_gleichzeitig_absent(monkeypatch):
    monkeypatch.setattr(mirror_repos.mirror_client, "fetch_sources_content", lambda slug: "content")
    monkeypatch.setattr(
        mirror_repos.mirror_client,
        "list_debian_repos",
        lambda: [{"value": "caddy", "label": "caddy"}, {"value": "nginx", "label": "nginx"}],
    )
    host = {"os_type": "debian", "mirror_repos": ["caddy"]}
    result = _result()

    mirror_repos.resolve_mirror_config_files(host, result)

    actions = {cf["path"]: cf["action"] for cf in result["config_files"]}
    assert actions["/etc/apt/sources.list.d/caddy.sources"] == "enforce"
    assert actions["/etc/apt/sources.list.d/nginx.sources"] == "absent"


def test_resolve_mirror_config_files_repo_liste_nicht_erreichbar_ueberspringt_cleanup_ohne_fehler(monkeypatch):
    """astrapi-mirror kurz nicht erreichbar fuer die Liste (list_debian_repos()
    liefert dann laut mirror_client [] zurueck) -- darf die Aufloesung der
    tatsaechlich ausgewaehlten Slugs nicht beeintraechtigen."""
    monkeypatch.setattr(mirror_repos.mirror_client, "fetch_sources_content", lambda slug: "content")
    monkeypatch.setattr(mirror_repos.mirror_client, "list_debian_repos", lambda: [])
    host = {"os_type": "debian", "mirror_repos": ["caddy"]}
    result = _result()

    mirror_repos.resolve_mirror_config_files(host, result)

    assert result["config_files"] == [
        {
            "path": "/etc/apt/sources.list.d/caddy.sources",
            "action": "enforce",
            "content": "content",
            "mode": "0644",
            "owner": "root",
            "group": "root",
            "force": False,
        }
    ]

"""hosts/ui/crud.py::_resolve_fields() -- markiert im mirror_repos-Feld
Optionen als 'locked', die der Host ueber eine seiner Gruppen bereits
geerbt hat (siehe field_renderer.html in astrapi-core: locked-Optionen
werden angehakt, aber nicht abwaehlbar dargestellt)."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts import mirror_client
from astrapi_admin.modules.hosts.ui import crud as hosts_crud


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _create_group(name: str, mirror_repos_: list[str]) -> str:
    from astrapi_admin.modules.host_groups.ui.crud import store as groups_store

    return groups_store.create(
        None, {"name": name, "description": "", "policy_ids": [], "mirror_repos": mirror_repos_, "enabled": True}
    )


def _fields():
    return [
        {"name": "mirror_repos", "type": "multiselect", "options_endpoint": "/api/hosts/mirror-repos-for-select"},
    ]


def test_resolve_fields_ohne_item_markiert_nichts_als_locked(monkeypatch):
    monkeypatch.setattr(
        mirror_client, "list_debian_repos", lambda: [{"value": "caddy", "label": "caddy"}]
    )

    resolved = hosts_crud._resolve_fields(_fields())

    opts = resolved[0]["options"]
    assert all("locked" not in o for o in opts)


def test_resolve_fields_markiert_gruppen_geerbte_optionen_als_locked(monkeypatch):
    monkeypatch.setattr(
        mirror_client,
        "list_debian_repos",
        lambda: [{"value": "caddy", "label": "caddy"}, {"value": "nginx", "label": "nginx"}],
    )
    gid = _create_group("basis", ["caddy"])
    item = {"group_ids": [gid]}

    resolved = hosts_crud._resolve_fields(_fields(), item)

    opts = {o["value"]: o for o in resolved[0]["options"]}
    assert opts["caddy"].get("locked") is True
    assert "locked" not in opts["nginx"]

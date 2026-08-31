"""hosts/ui/crud.py::_resolve_fields() -- markiert im mirror_repos- UND
im policy_ids-Feld Optionen als 'locked', die der Host ueber eine seiner
Gruppen bereits geerbt hat (siehe field_renderer.html in astrapi-core:
locked-Optionen werden angehakt, aber nicht abwaehlbar dargestellt)."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts import mirror_client
from astrapi_admin.modules.hosts.ui import crud as hosts_crud
from astrapi_admin.modules.policies import engine as policies_engine


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _create_group(name: str, mirror_repos_: list[str] | None = None, policy_ids: list[str] | None = None) -> str:
    from astrapi_admin.modules.host_groups.ui.crud import store as groups_store

    return groups_store.create(
        None,
        {
            "name": name,
            "description": "",
            "policy_ids": policy_ids or [],
            "mirror_repos": mirror_repos_ or [],
            "enabled": True,
        },
    )


def _fields():
    return [
        {"name": "mirror_repos", "type": "multiselect", "options_endpoint": "/api/hosts/mirror-repos-for-select"},
        {"name": "policy_ids", "type": "multiselect", "options_endpoint": "/api/policies/for-select"},
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


def test_resolve_fields_markiert_gruppen_geerbte_policy_als_locked(monkeypatch):
    monkeypatch.setattr(mirror_client, "list_debian_repos", lambda: [])
    policies_engine.create_policy("p1", {"name": "vim", "enabled": True})
    policies_engine.create_policy("p2", {"name": "zsh", "enabled": True})
    gid = _create_group("basis", policy_ids=["p1"])
    item = {"group_ids": [gid]}

    resolved = hosts_crud._resolve_fields(_fields(), item)

    policy_field = next(f for f in resolved if f["name"] == "policy_ids")
    opts = {o["value"]: o for o in policy_field["options"]}
    assert opts["p1"].get("locked") is True
    assert "locked" not in opts["p2"]


def test_resolve_fields_direkt_zugewiesene_policy_wird_nicht_gesperrt(monkeypatch):
    """Eine Policy, die der Host direkt (nicht ueber eine Gruppe) hat,
    bleibt frei abwaehlbar -- nur der Gruppen-Anteil wird gesperrt."""
    monkeypatch.setattr(mirror_client, "list_debian_repos", lambda: [])
    policies_engine.create_policy("p1", {"name": "vim", "enabled": True})
    item = {"group_ids": [], "policy_ids": ["p1"]}

    resolved = hosts_crud._resolve_fields(_fields(), item)

    policy_field = next(f for f in resolved if f["name"] == "policy_ids")
    opts = {o["value"]: o for o in policy_field["options"]}
    assert "locked" not in opts["p1"]

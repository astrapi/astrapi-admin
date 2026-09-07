"""user_policies/engine.py::resolve_users_for_host() -- E-012 (direkt
zugewiesene user_policy_ids) plus seit astrapi-hub-Vault E-013 auch über
Host-Gruppen zuweisbar, mit demselben Tier-Vorrangsmuster wie
policies/engine.py::resolve_policy_for_host() (direkte Zuweisung schlägt
Gruppen-Zuweisung). Entries werden nach Username vereinigt; zwei Policies
auf derselben Vorrangstufe mit demselben Username, aber abweichender
Definition, sind ein Konflikt statt still aufgelöst zu werden."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.host_groups.ui.crud import store as groups_store
from astrapi_admin.modules.user_policies import engine as up_engine


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _host(**overrides):
    base = {"group_ids": [], "user_policy_ids": []}
    base.update(overrides)
    return base


def _create_group(name: str, user_policy_ids: list[str]) -> str:
    return groups_store.create(
        None,
        {"name": name, "description": "", "policy_ids": [], "user_policy_ids": user_policy_ids,
         "mirror_repos": [], "enabled": True},
    )


def _entry(username="alice", action="enforce", shell="/bin/bash", sudo=False, ssh_keys=None):
    return {
        "username": username,
        "action": action,
        "shell": shell,
        "sudo": sudo,
        "ssh_keys": ssh_keys or [],
    }


def test_resolve_users_for_host_liefert_entries_der_zugewiesenen_policy():
    up_engine.create_user_policy("p1", {"name": "base", "enabled": True, "entries": [_entry("alice", sudo=True)]})
    host = _host(user_policy_ids=["p1"])

    result = up_engine.resolve_users_for_host(host)

    assert result["users"] == [_entry("alice", sudo=True)]
    assert result["conflicts"] == []


def test_resolve_users_for_host_ohne_zugewiesene_policy_ist_leer():
    result = up_engine.resolve_users_for_host(_host())

    assert result == {"users": [], "conflicts": []}


def test_resolve_users_for_host_ignoriert_deaktivierte_policy():
    up_engine.create_user_policy("p1", {"name": "base", "enabled": False, "entries": [_entry("alice")]})
    host = _host(user_policy_ids=["p1"])

    result = up_engine.resolve_users_for_host(host)

    assert result["users"] == []


def test_resolve_users_for_host_vereinigt_mehrere_policies():
    up_engine.create_user_policy("p1", {"name": "a", "enabled": True, "entries": [_entry("alice")]})
    up_engine.create_user_policy("p2", {"name": "b", "enabled": True, "entries": [_entry("bob")]})
    host = _host(user_policy_ids=["p1", "p2"])

    result = up_engine.resolve_users_for_host(host)

    usernames = {u["username"] for u in result["users"]}
    assert usernames == {"alice", "bob"}


def test_resolve_users_for_host_identische_definition_kein_konflikt():
    """Derselbe Username in zwei Policies mit IDENTISCHER Definition ist
    kein Konflikt -- nur eine abweichende Definition ist einer."""
    up_engine.create_user_policy("p1", {"name": "a", "enabled": True, "entries": [_entry("alice", sudo=True)]})
    up_engine.create_user_policy("p2", {"name": "b", "enabled": True, "entries": [_entry("alice", sudo=True)]})
    host = _host(user_policy_ids=["p1", "p2"])

    result = up_engine.resolve_users_for_host(host)

    assert result["conflicts"] == []
    assert len(result["users"]) == 1


def test_resolve_users_for_host_abweichende_definition_ist_konflikt():
    up_engine.create_user_policy("p1", {"name": "a", "enabled": True, "entries": [_entry("alice", sudo=True)]})
    up_engine.create_user_policy("p2", {"name": "b", "enabled": True, "entries": [_entry("alice", sudo=False)]})
    host = _host(user_policy_ids=["p1", "p2"])

    result = up_engine.resolve_users_for_host(host)

    assert result["conflicts"] == [{"type": "user", "username": "alice"}]
    assert result["users"] == []


def test_resolve_users_for_host_ignoriert_eintraege_ohne_username():
    up_engine.create_user_policy("p1", {"name": "a", "enabled": True, "entries": [_entry("")]})
    host = _host(user_policy_ids=["p1"])

    result = up_engine.resolve_users_for_host(host)

    assert result["users"] == []


def test_group_user_policy_ids_vereinigt_mehrere_gruppen():
    up_engine.create_user_policy("p1", {"name": "a", "enabled": True, "entries": []})
    up_engine.create_user_policy("p2", {"name": "b", "enabled": True, "entries": []})
    g1 = _create_group("g1", ["p1"])
    g2 = _create_group("g2", ["p1", "p2"])

    result = up_engine.group_user_policy_ids({"group_ids": [g1, g2]})

    assert result == {"p1", "p2"}


def test_group_user_policy_ids_geloeschte_gruppe_wird_uebersprungen():
    assert up_engine.group_user_policy_ids({"group_ids": ["nie-angelegt"]}) == set()


def test_resolve_users_for_host_gruppen_geerbte_policy_wird_angewendet():
    """Eine Nutzer-Policy, die nur ueber eine Gruppe zugewiesen ist (nicht
    direkt am Host), muss trotzdem einfliessen -- der eigentliche Zweck
    von E-013 (claude-deploy ueber mehrere Dev-Hosts buendeln)."""
    up_engine.create_user_policy("p1", {"name": "deploy", "enabled": True, "entries": [_entry("claude-deploy")]})
    gid = _create_group("dev-hosts", ["p1"])
    host = _host(group_ids=[gid])

    result = up_engine.resolve_users_for_host(host)

    assert result["users"] == [_entry("claude-deploy")]
    assert result["conflicts"] == []


def test_resolve_users_for_host_direkte_zuweisung_dupliziert_nicht_mit_gruppe():
    """Dieselbe Policy sowohl direkt als auch ueber eine Gruppe zugewiesen
    -- darf nicht zu einem kuenstlichen Konflikt mit sich selbst fuehren."""
    up_engine.create_user_policy("p1", {"name": "deploy", "enabled": True, "entries": [_entry("claude-deploy")]})
    gid = _create_group("dev-hosts", ["p1"])
    host = _host(group_ids=[gid], user_policy_ids=["p1"])

    result = up_engine.resolve_users_for_host(host)

    assert result["users"] == [_entry("claude-deploy")]
    assert result["conflicts"] == []


def test_resolve_users_for_host_direkte_zuweisung_schlaegt_abweichende_gruppen_zuweisung():
    """Unterschiedliche Definition desselben Usernamens direkt vs. ueber
    Gruppe -- direkt gewinnt eindeutig, kein Konflikt (andere Tier-Stufe)."""
    up_engine.create_user_policy("p1", {"name": "direkt", "enabled": True, "entries": [_entry("claude-deploy", sudo=True)]})
    up_engine.create_user_policy("p2", {"name": "gruppe", "enabled": True, "entries": [_entry("claude-deploy", sudo=False)]})
    gid = _create_group("dev-hosts", ["p2"])
    host = _host(group_ids=[gid], user_policy_ids=["p1"])

    result = up_engine.resolve_users_for_host(host)

    assert result["conflicts"] == []
    assert result["users"] == [_entry("claude-deploy", sudo=True)]


def test_resolve_users_for_host_konflikt_zwischen_zwei_gruppen():
    """Zwei Gruppen mit abweichender Definition desselben Usernamens --
    beide auf derselben (Gruppen-)Tier-Stufe, also echter Konflikt."""
    up_engine.create_user_policy("p1", {"name": "a", "enabled": True, "entries": [_entry("claude-deploy", sudo=True)]})
    up_engine.create_user_policy("p2", {"name": "b", "enabled": True, "entries": [_entry("claude-deploy", sudo=False)]})
    g1 = _create_group("g1", ["p1"])
    g2 = _create_group("g2", ["p2"])
    host = _host(group_ids=[g1, g2])

    result = up_engine.resolve_users_for_host(host)

    assert result["conflicts"] == [{"type": "user", "username": "claude-deploy"}]
    assert result["users"] == []


def test_user_policies_for_select_liefert_name_als_label():
    up_engine.create_user_policy("p1", {"name": "base-admins", "enabled": True, "entries": []})

    result = up_engine.user_policies_for_select()

    assert result == [{"value": "p1", "label": "base-admins"}]

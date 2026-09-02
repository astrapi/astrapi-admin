"""user_policies/engine.py::resolve_users_for_host() -- E-012: nur direkt
zugewiesene user_policy_ids (kein Gruppen-Erbe in dieser Runde, siehe
Nächster Schritt in T-296-ADMIN). Entries werden nach Username vereinigt;
zwei Policies mit demselben Username, aber abweichender Definition, sind
ein Konflikt statt still aufgelöst zu werden -- gleiche Vorsicht wie
policies/engine.py::resolve_policy_for_host()."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.user_policies import engine as up_engine


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _host(**overrides):
    base = {"user_policy_ids": []}
    base.update(overrides)
    return base


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


def test_user_policies_for_select_liefert_name_als_label():
    up_engine.create_user_policy("p1", {"name": "base-admins", "enabled": True, "entries": []})

    result = up_engine.user_policies_for_select()

    assert result == [{"value": "p1", "label": "base-admins"}]

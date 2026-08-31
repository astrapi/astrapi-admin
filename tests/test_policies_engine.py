"""policies/engine.py::resolve_policy_for_host() -- Integration mit
Templates. Die bereits bestehende Tier-/Konfliktlogik bleibt unverändert
(siehe _load()); hier nur der neue Erweiterungspunkt: eine Policy mit
template_id liefert dieselbe Form wie eine rohe Policy, und ein kaputtes
Template darf nicht die Auflösung für andere Policies/Hosts mitreißen."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.host_groups.ui.crud import store as groups_store
from astrapi_admin.modules.policies import engine as policies_engine
from astrapi_admin.modules.templates import engine as templates_engine


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _host(**overrides):
    base = {"os_type": "archlinux", "group_ids": [], "policy_ids": []}
    base.update(overrides)
    return base


def _caddy_template():
    return {
        "name": "Caddy",
        "enabled": True,
        "packages_arch": {"present": ["caddy"], "absent": []},
        "packages_debian": {"present": ["caddy"], "absent": []},
        "services": [{"name": "caddy", "state": "enabled_started"}],
        "config_files": [
            {
                "path": "/etc/caddy/Caddyfile",
                "action": "enforce",
                "content": "{{ domain }} {\n    reverse_proxy {{ upstream }}\n}\n",
                "mode": "0644",
                "owner": "root",
                "group": "root",
            }
        ],
        "params": [
            {"key": "domain", "label": "Domain", "default": None, "required": True},
            {"key": "upstream", "label": "Upstream", "default": "127.0.0.1:8080", "required": False},
        ],
    }


def test_resolve_policy_for_host_mit_template_liefert_gerenderte_config():
    templates_engine.create_template("caddy", _caddy_template())
    policies_engine.create_policy(
        "p1",
        {
            "name": "Caddy für Blog",
            "enabled": True,
            "template_id": "caddy",
            "template_params": {"domain": "blog.example.org"},
        },
    )
    host = _host(policy_ids=["p1"])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["status"] == "ok"
    assert result["packages_present"] == ["caddy"]
    assert len(result["config_files"]) == 1
    assert "blog.example.org {" in result["config_files"][0]["content"]
    assert "reverse_proxy 127.0.0.1:8080" in result["config_files"][0]["content"]
    assert result["template_errors"] == []


def test_resolve_policy_for_host_kaputtes_template_bricht_nicht_andere_policies():
    templates_engine.create_template("caddy", _caddy_template())
    # p1 referenziert das Template, aber ohne den Pflichtparameter 'domain'.
    policies_engine.create_policy(
        "p1", {"name": "kaputt", "enabled": True, "template_id": "caddy", "template_params": {}}
    )
    # p2 ist eine ganz normale, unabhängige Policy.
    policies_engine.create_policy(
        "p2",
        {
            "name": "Baseline",
            "enabled": True,
            "packages_arch": {"present": ["htop"], "absent": []},
            "packages_debian": {"present": [], "absent": []},
            "config_files": [],
            "services": [],
        },
    )
    host = _host(policy_ids=["p1", "p2"])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["status"] == "conflict"
    assert len(result["template_errors"]) == 1
    assert result["template_errors"][0]["policy_id"] == "p1"
    assert result["template_errors"][0]["template_id"] == "caddy"
    # p2 trägt trotzdem normal bei -- ein kaputtes Template reißt nicht
    # die ganze Host-Auflösung mit.
    assert result["packages_present"] == ["htop"]


def test_resolve_policy_for_host_ohne_template_verhaelt_sich_wie_vorher():
    """Reine Regression: eine rohe Policy ohne template_id läuft exakt wie
    vor der Template-Erweiterung durch _load()."""
    policies_engine.create_policy(
        "p1",
        {
            "name": "Baseline",
            "enabled": True,
            "packages_arch": {"present": ["vim"], "absent": []},
            "packages_debian": {"present": [], "absent": []},
            "config_files": [],
            "services": [{"name": "sshd", "state": "enabled_started"}],
        },
    )
    host = _host(policy_ids=["p1"])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["status"] == "ok"
    assert result["packages_present"] == ["vim"]
    assert result["services"] == [{"name": "sshd", "state": "enabled_started"}]
    assert result["template_errors"] == []


def test_resolve_policy_for_host_geloeschtes_template_meldet_template_error():
    templates_engine.create_template("caddy", _caddy_template())
    policies_engine.create_policy(
        "p1",
        {
            "name": "verwaist",
            "enabled": True,
            "template_id": "caddy",
            "template_params": {"domain": "x.org"},
        },
    )
    templates_engine.delete_template("caddy")
    host = _host(policy_ids=["p1"])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["status"] == "conflict"
    assert result["template_errors"][0]["policy_id"] == "p1"


def test_groups_store_importierbar():
    """Reiner Smoke-Test, dass der Import in resolve_policy_for_host()
    weiterhin funktioniert (host_groups-Modul unveraendert)."""
    assert groups_store.list() == {}


def test_resolve_policy_for_host_gibt_force_flag_weiter():
    """config_files[].force muss bis zum Agenten durchgereicht werden --
    sonst kann die Fremdbesitz-Ausnahme (z.B. Caddy-Template ersetzt die
    vom Paket mitgelieferte Caddyfile) nie greifen."""
    policies_engine.create_policy(
        "p1",
        {
            "name": "erzwungen",
            "enabled": True,
            "config_files": [
                {"path": "/etc/caddy/Caddyfile", "action": "enforce", "content": "x", "force": True}
            ],
        },
    )
    host = _host(policy_ids=["p1"])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["config_files"][0]["force"] is True


def test_resolve_policy_for_host_force_unterschied_ist_ein_konflikt():
    """Zwei Policies auf derselben Vorrangstufe, die sich nur im
    force-Flag unterscheiden, duerfen nicht still aufgeloest werden --
    das ist ein echter Unterschied im gewuenschten Verhalten."""
    policies_engine.create_policy(
        "p1",
        {
            "name": "geschuetzt",
            "enabled": True,
            "config_files": [{"path": "/etc/x.conf", "action": "enforce", "content": "x", "force": False}],
        },
    )
    policies_engine.create_policy(
        "p2",
        {
            "name": "erzwungen",
            "enabled": True,
            "config_files": [{"path": "/etc/x.conf", "action": "enforce", "content": "x", "force": True}],
        },
    )
    host = _host(policy_ids=["p1", "p2"])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["status"] == "conflict"
    assert result["conflicts"] == [{"type": "config_file", "path": "/etc/x.conf"}]

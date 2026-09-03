"""policies/engine.py::resolve_policy_for_host() -- Kernauflösung nach
E-004 (kein Template-System mehr, Pakete sind ein reiner "muss vorhanden
sein"-Existenz-Check ohne Tier-/Konfliktlogik, da additiv nie
widersprüchlich)."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.host_groups.ui.crud import store as groups_store
from astrapi_admin.modules.policies import engine as policies_engine


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _host(**overrides):
    base = {"os_type": "archlinux", "group_ids": [], "policy_ids": []}
    base.update(overrides)
    return base


def test_resolve_policy_for_host_liefert_benoetigte_pakete_config_und_services():
    policies_engine.create_policy(
        "p1",
        {
            "name": "Baseline",
            "enabled": True,
            "packages_arch": ["vim"],
            "packages_debian": [],
            "config_files": [],
            "services": [{"name": "sshd", "state": "enabled_started"}],
        },
    )
    host = _host(policy_ids=["p1"])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["status"] == "ok"
    assert result["packages_required"] == ["vim"]
    assert result["services"] == [{"name": "sshd", "state": "enabled_started"}]
    assert result["conflicts"] == []


def test_resolve_policy_for_host_pakete_aus_mehreren_policies_werden_vereinigt():
    """Anders als frueher (present vs. absent) kann sich ein reiner
    Existenz-Check nie widersprechen -- zwei Policies, die dasselbe oder
    unterschiedliche Pakete fordern, werden einfach vereinigt, kein
    Konflikt moeglich."""
    policies_engine.create_policy("p1", {"name": "a", "enabled": True, "packages_arch": ["caddy"]})
    policies_engine.create_policy("p2", {"name": "b", "enabled": True, "packages_arch": ["caddy", "htop"]})
    host = _host(policy_ids=["p1", "p2"])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["status"] == "ok"
    assert result["packages_required"] == ["caddy", "htop"]


def test_groups_store_importierbar():
    """Reiner Smoke-Test, dass der Import in resolve_policy_for_host()
    weiterhin funktioniert (host_groups-Modul unveraendert)."""
    assert groups_store.list() == {}


def test_resolve_policy_for_host_gibt_force_flag_weiter():
    """config_files[].force muss bis zum Agenten durchgereicht werden --
    sonst kann die Fremdbesitz-Ausnahme (z.B. Caddy-Policy ersetzt die
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


def _create_group(name: str, policy_ids: list[str]) -> str:
    return groups_store.create(
        None, {"name": name, "description": "", "policy_ids": policy_ids, "mirror_repos": [], "enabled": True}
    )


def test_group_policy_ids_vereinigt_mehrere_gruppen():
    policies_engine.create_policy("p1", {"name": "a", "enabled": True})
    policies_engine.create_policy("p2", {"name": "b", "enabled": True})
    g1 = _create_group("g1", ["p1"])
    g2 = _create_group("g2", ["p1", "p2"])

    result = policies_engine.group_policy_ids({"group_ids": [g1, g2]})

    assert result == {"p1", "p2"}


def test_group_policy_ids_geloeschte_gruppe_wird_uebersprungen():
    assert policies_engine.group_policy_ids({"group_ids": ["nie-angelegt"]}) == set()


def test_resolve_policy_for_host_gruppen_geerbte_policy_wird_angewendet():
    """Regressionsschutz fuer den group_policy_ids()-Refactor: eine Policy,
    die nur ueber eine Gruppe zugewiesen ist (nicht direkt am Host), muss
    weiterhin einfliessen."""
    policies_engine.create_policy(
        "p1",
        {"name": "vim", "enabled": True, "packages_arch": ["vim"], "services": []},
    )
    gid = _create_group("basis", ["p1"])
    host = _host(group_ids=[gid], policy_ids=[])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["status"] == "ok"
    assert result["packages_required"] == ["vim"]


def test_resolve_policy_for_host_direkte_zuweisung_dupliziert_nicht_mit_gruppe():
    """Dieselbe Policy sowohl direkt als auch ueber eine Gruppe zugewiesen
    -- darf nicht zu einem (kuenstlichen) Konflikt mit sich selbst fuehren."""
    policies_engine.create_policy(
        "p1",
        {"name": "vim", "enabled": True, "packages_arch": ["vim"]},
    )
    gid = _create_group("basis", ["p1"])
    host = _host(group_ids=[gid], policy_ids=["p1"])

    result = policies_engine.resolve_policy_for_host(host)

    assert result["status"] == "ok"
    assert result["packages_required"] == ["vim"]


def test_policies_for_select_zeigt_alles_ohne_filter():
    """host_groups/config/schema.yaml haengt kein ?context=host an --
    dort muss auch eine group_only-Policy waehlbar bleiben."""
    policies_engine.create_policy("p1", {"name": "normal", "enabled": True})
    policies_engine.create_policy("p2", {"name": "nur-gruppen", "enabled": True, "group_only": True})

    result = policies_engine.policies_for_select()

    assert {o["value"] for o in result} == {"p1", "p2"}


def test_policies_for_select_blendet_group_only_fuer_host_kontext_aus():
    """hosts/config/schema.yaml haengt ?context=host an -- exclude_group_only
    muss die Policy dort aus der Direkt-Zuweisung nehmen."""
    policies_engine.create_policy("p1", {"name": "normal", "enabled": True})
    policies_engine.create_policy("p2", {"name": "nur-gruppen", "enabled": True, "group_only": True})

    result = policies_engine.policies_for_select(exclude_group_only=True)

    assert {o["value"] for o in result} == {"p1"}


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

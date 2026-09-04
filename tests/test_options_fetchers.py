"""Regressionsschutz für den Bug "Policy lässt sich keinem Host zuweisen"
(T-270-ADMIN): hosts.policy_ids/group_ids und host_groups.policy_ids
nutzen options_endpoint (astrapi_core.ui.field_resolver), das ohne einen
per register_options_fetcher() registrierten Prefix still `[]` liefert --
kein Fehler sichtbar, das Multiselect im Dialog bleibt einfach leer.
Beide Module müssen ihren Fetcher beim Import registrieren (Vorbild:
astrapi_sync/modules/folders/__init__.py)."""
import pytest
from astrapi_core.system import db
from astrapi_core.ui.field_resolver import resolve_options_endpoint


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def test_policies_options_endpoint_liefert_echte_daten():
    # Import triggert modules/policies/__init__.py (Registrierung als
    # Modul-Ladeseiteneffekt) -- gleiches Prinzip wie in der echten App
    # (module_registry.load_modules() importiert jedes Modulpaket einmal).
    from astrapi_admin.modules.policies import engine as policies_engine

    policies_engine.create_policy("p1", {"name": "Baseline", "enabled": True})

    resolved = resolve_options_endpoint(
        [{"name": "policy_ids", "type": "multiselect", "options_endpoint": "/api/policies/for-select"}]
    )

    assert resolved[0]["options"] == [{"value": "p1", "label": "Baseline"}]


def test_policies_options_endpoint_context_host_blendet_group_only_aus():
    """hosts/config/schema.yaml haengt ?context=host an den Endpoint an --
    eine group_only-Policy darf dort nicht in der Direkt-Zuweisung
    auftauchen."""
    from astrapi_admin.modules.policies import engine as policies_engine

    policies_engine.create_policy("p1", {"name": "Baseline", "enabled": True})
    policies_engine.create_policy("p2", {"name": "Caddy", "enabled": True, "group_only": True})

    resolved = resolve_options_endpoint(
        [
            {
                "name": "policy_ids",
                "type": "multiselect",
                "options_endpoint": "/api/policies/for-select?context=host",
            }
        ]
    )

    assert resolved[0]["options"] == [{"value": "p1", "label": "Baseline"}]


def test_policies_options_endpoint_context_group_blendet_einzel_policies_aus():
    """host_groups/config/schema.yaml haengt ?context=group an -- die
    umgekehrte Sperre: eine normale Einzel-Policy (group_only=False) darf
    dort nicht mehr auftauchen (Nutzerentscheidung 2026-09-04, harte statt
    informative Trennung)."""
    from astrapi_admin.modules.policies import engine as policies_engine

    policies_engine.create_policy("p1", {"name": "Baseline", "enabled": True})
    policies_engine.create_policy("p2", {"name": "Caddy", "enabled": True, "group_only": True})

    resolved = resolve_options_endpoint(
        [
            {
                "name": "policy_ids",
                "type": "multiselect",
                "options_endpoint": "/api/policies/for-select?context=group",
            }
        ]
    )

    assert resolved[0]["options"] == [{"value": "p2", "label": "Caddy"}]


def test_host_groups_options_endpoint_liefert_echte_daten():
    from astrapi_admin.modules.host_groups.ui.crud import store as groups_store

    groups_store.create(None, {"name": "LXCs", "description": "", "policy_ids": [], "enabled": True})

    resolved = resolve_options_endpoint(
        [{"name": "group_ids", "type": "multiselect", "options_endpoint": "/api/host_groups/for-select"}]
    )

    assert len(resolved[0]["options"]) == 1
    assert resolved[0]["options"][0]["label"] == "LXCs"


def test_unbekannter_options_endpoint_liefert_weiterhin_leere_liste():
    """Kein Regressionstest gegen den Fix, sondern gegen das Feature selbst:
    ein wirklich unbekannter Prefix soll (wie dokumentiert) still [] liefern,
    nicht crashen."""
    resolved = resolve_options_endpoint(
        [{"name": "x", "type": "multiselect", "options_endpoint": "/api/nie-registriert/for-select"}]
    )
    assert resolved[0]["options"] == []

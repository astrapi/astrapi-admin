"""api/agent.py -- Update-Status (E-007): pending_action wird im
Policy-Abruf sichtbar, ein Report mit update_result setzt es wieder
zurueck, updates_available/updates_checked_at werden aus dem Report
uebernommen. Kein Automatismus -- pending_action wird ausschliesslich
ueber hosts/ui/updates.py::trigger_update() explizit gesetzt."""
import pytest
from astrapi_core.system import db
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrapi_admin.api.agent import router as agent_router
from astrapi_admin.api.auth import hash_token


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(agent_router)
    return TestClient(app)


def _create_host(**overrides) -> tuple[str, str]:
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    token = "test-token-123"
    values = {
        "hostname": "lxc99",
        "label": "lxc99",
        "os_type": "debian",
        "group_ids": [],
        "policy_ids": [],
        "mirror_repos": [],
        "token_hash": hash_token(token),
        "last_seen": "",
        "last_report": "",
        "last_status": "",
        "pending_action": "",
        "updates_available": -1,
        "updates_checked_at": "",
        "enabled": True,
    }
    values.update(overrides)
    host_id = hosts_store.create(None, values)
    return str(host_id), token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_get_policy_liefert_leeres_pending_action_per_default(client):
    _host_id, token = _create_host()

    r = client.get("/api/agent/policy", headers=_auth(token))

    assert r.status_code == 200
    assert r.json()["pending_action"] == ""


def test_get_policy_gibt_gesetztes_pending_action_weiter(client):
    host_id, token = _create_host(pending_action="update")

    r = client.get("/api/agent/policy", headers=_auth(token))

    assert r.json()["pending_action"] == "update"


def test_post_report_uebernimmt_updates_available(client):
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host()

    r = client.post(
        "/api/agent/report",
        json={"status": "ok", "summary": "keine Änderungen nötig", "details": {"updates_available": 4}},
        headers=_auth(token),
    )

    assert r.status_code == 200
    host = hosts_store.get(host_id)
    assert host["updates_available"] == 4
    assert host["updates_checked_at"] != ""


def test_post_report_mit_update_result_loescht_pending_action(client):
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host(pending_action="update")

    r = client.post(
        "/api/agent/report",
        json={
            "status": "ok",
            "summary": "aktualisiert",
            "details": {"updates_available": 0, "update_result": {"ok": True, "detail": "..."}},
        },
        headers=_auth(token),
    )

    assert r.status_code == 200
    host = hosts_store.get(host_id)
    assert host["pending_action"] == ""


def test_post_report_ohne_update_result_laesst_pending_action_unangetastet(client):
    """Ein ganz normaler Policy-Report (kein Update angefordert/versucht)
    darf ein bereits gesetztes pending_action nicht versehentlich loeschen."""
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host(pending_action="update")

    client.post(
        "/api/agent/report",
        json={"status": "ok", "summary": "keine Änderungen nötig", "details": {"updates_available": 2}},
        headers=_auth(token),
    )

    host = hosts_store.get(host_id)
    assert host["pending_action"] == "update"


def test_post_report_fehlgeschlagenes_update_loescht_pending_action_trotzdem(client):
    """Sonst bliebe ein fehlgeschlagenes Update fuer immer 'pending' und
    wuerde bei jedem Zyklus stumpf wiederholt."""
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host(pending_action="update")

    client.post(
        "/api/agent/report",
        json={
            "status": "error",
            "summary": "Update fehlgeschlagen",
            "details": {"updates_available": 4, "update_result": {"ok": False, "detail": "network error"}},
        },
        headers=_auth(token),
    )

    host = hosts_store.get(host_id)
    assert host["pending_action"] == ""

"""api/agent.py::pair() -- Proxmox-LXC-Erkennung beim Pairing/Neu-Verbinden
(E-009): best-effort, darf das Pairing selbst nie zum Scheitern bringen."""
from unittest.mock import patch

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


def _pairing_token(host_id=None) -> str:
    from astrapi_admin.modules.hosts.pairing_store import create_pairing_token

    return create_pairing_token(host_id=host_id)


def test_pair_neuer_host_erkennt_proxmox_lxc(client):
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    token = _pairing_token()
    with patch(
        "astrapi_admin.modules.hosts.proxmox_client.find_lxc_by_hostname",
        return_value={"vmid": 105, "node": "pve2"},
    ):
        r = client.post("/api/agent/pair", json={"token": token, "hostname": "lxc99", "os_type": "debian"})

    assert r.status_code == 200
    host = hosts_store.get(str(r.json()["host_id"]))
    assert host["proxmox_vmid"] == 105


def test_pair_neuer_host_ohne_proxmox_bleibt_minus_eins(client):
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    token = _pairing_token()
    with patch("astrapi_admin.modules.hosts.proxmox_client.find_lxc_by_hostname", return_value=None):
        r = client.post("/api/agent/pair", json={"token": token, "hostname": "lxc99", "os_type": "debian"})

    host = hosts_store.get(str(r.json()["host_id"]))
    assert host["proxmox_vmid"] == -1


def test_pair_bricht_nicht_ab_wenn_proxmox_erkennung_ausnahme_wirft(client):
    """Ein defektes/nicht erreichbares Proxmox darf das Pairing selbst
    nicht scheitern lassen -- best-effort."""
    token = _pairing_token()
    with patch(
        "astrapi_admin.modules.hosts.proxmox_client.find_lxc_by_hostname",
        side_effect=RuntimeError("boom"),
    ):
        r = client.post("/api/agent/pair", json={"token": token, "hostname": "lxc99", "os_type": "debian"})

    assert r.status_code == 200


def test_pair_reconnect_erkennt_proxmox_nachtraeglich(client):
    """Bestandshosts, die vor E-009 gepairt wurden, bekommen die
    Erkennung ueber 'Neu verbinden' nachgezogen, ohne eigenen
    Zusatz-Workflow."""
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id = hosts_store.create(None, {
        "hostname": "lxc-bestand",
        "label": "lxc-bestand",
        "os_type": "debian",
        "group_ids": [], "policy_ids": [],
        "token_hash": hash_token("alt"),
        "last_seen": "", "last_report": "", "last_status": "",
        "proxmox_vmid": -1,
        "enabled": True,
    })

    token = _pairing_token(host_id=str(host_id))
    with patch(
        "astrapi_admin.modules.hosts.proxmox_client.find_lxc_by_hostname",
        return_value={"vmid": 108, "node": "pve1"},
    ):
        r = client.post("/api/agent/pair", json={"token": token, "hostname": "lxc-bestand"})

    assert r.status_code == 200
    host = hosts_store.get(str(host_id))
    assert host["proxmox_vmid"] == 108

"""api/agent.py -- Update-Status (E-007) + Security-Update-Erkennung/
Benachrichtigung (E-008): pending_action wird im Policy-Abruf sichtbar,
ein Report mit update_result setzt es wieder zurueck,
updates_available/security_updates_available/updates_checked_at werden
aus dem Report uebernommen, eine gestiegene Update-Anzahl loest (falls
in astrapi-core::notify konfiguriert) eine Benachrichtigung aus. Kein
Automatismus -- pending_action wird ausschliesslich ueber
hosts/ui/updates.py::trigger_update() explizit gesetzt."""
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


def test_get_policy_liefert_poll_interval_minutes_default(client):
    """E-011: Default 15 ohne gesetztes Setting."""
    _host_id, token = _create_host()

    r = client.get("/api/agent/policy", headers=_auth(token))

    assert r.json()["poll_interval_minutes"] == 15


def test_get_policy_ohne_gesetzte_zeitzone_fehlt_das_feld(client):
    """T-321-ADMIN: kein Feld, wenn nichts konfiguriert ist -- der Agent
    soll die Zeitzone dann unangetastet lassen, nicht auf "" setzen."""
    _host_id, token = _create_host()

    r = client.get("/api/agent/policy", headers=_auth(token))

    assert "timezone" not in r.json()


def test_get_policy_liefert_gesetzte_zeitzone(client):
    from astrapi_core.ui import settings_registry

    settings_registry.set_module("hosts", "agent_timezone", "Europe/Berlin")
    _host_id, token = _create_host()

    r = client.get("/api/agent/policy", headers=_auth(token))

    assert r.json()["timezone"] == "Europe/Berlin"


def test_post_report_uebernimmt_reboot_required(client):
    """T-298-ADMIN."""
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host()

    r = client.post(
        "/api/agent/report",
        json={"status": "ok", "summary": "keine Änderungen nötig", "details": {"reboot_required": True}},
        headers=_auth(token),
    )

    assert r.status_code == 200
    host = hosts_store.get(host_id)
    assert host["reboot_required"]


def test_get_policy_liefert_zugewiesene_nutzer(client):
    """E-012."""
    from astrapi_admin.modules.user_policies import engine as up_engine

    up_engine.create_user_policy(
        "up1", {"name": "base", "enabled": True, "entries": [{"username": "alice", "action": "enforce"}]}
    )
    _host_id, token = _create_host(user_policy_ids=["up1"])

    r = client.get("/api/agent/policy", headers=_auth(token))

    assert r.json()["users"] == [{"username": "alice", "action": "enforce"}]


def test_get_policy_ohne_nutzer_policy_liefert_leere_liste(client):
    _host_id, token = _create_host()

    r = client.get("/api/agent/policy", headers=_auth(token))

    assert r.json()["users"] == []


def test_get_policy_nutzer_konflikt_landet_in_der_gemeinsamen_conflicts_liste(client):
    from astrapi_admin.modules.user_policies import engine as up_engine

    up_engine.create_user_policy(
        "up1", {"name": "a", "enabled": True, "entries": [{"username": "alice", "action": "enforce", "sudo": True}]}
    )
    up_engine.create_user_policy(
        "up2", {"name": "b", "enabled": True, "entries": [{"username": "alice", "action": "enforce", "sudo": False}]}
    )
    _host_id, token = _create_host(user_policy_ids=["up1", "up2"])

    r = client.get("/api/agent/policy", headers=_auth(token))

    assert {"type": "user", "username": "alice"} in r.json()["conflicts"]


def test_post_report_uebernimmt_user_inventory(client):
    """E-012."""
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host()
    inventory = [{"username": "alice", "uid": 1500, "shell": "/bin/bash", "sudo": True, "has_ssh_keys": True, "managed": True}]

    r = client.post(
        "/api/agent/report",
        json={"status": "ok", "summary": "keine Änderungen nötig", "details": {"user_inventory": inventory}},
        headers=_auth(token),
    )

    assert r.status_code == 200
    host = hosts_store.get(host_id)
    import json

    assert json.loads(host["user_inventory"]) == inventory
    assert host["user_inventory_checked_at"] != ""


def test_post_report_ohne_user_inventory_feld_laesst_spalte_unangetastet(client):
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host(user_inventory="[]")

    client.post(
        "/api/agent/report",
        json={"status": "ok", "summary": "keine Änderungen nötig", "details": {"updates_available": 0}},
        headers=_auth(token),
    )

    host = hosts_store.get(host_id)
    assert host["user_inventory"] == "[]"


def test_post_report_ohne_reboot_required_feld_laesst_spalte_unangetastet(client):
    """Ein aelterer, noch nicht aktualisierter Agent kennt das Feld nicht --
    ein unconditionales False duerfte einen bereits erkannten, echten
    Neustart-Bedarf nicht faelschlich zuruecksetzen."""
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host(reboot_required=True)

    client.post(
        "/api/agent/report",
        json={"status": "ok", "summary": "keine Änderungen nötig", "details": {"updates_available": 0}},
        headers=_auth(token),
    )

    host = hosts_store.get(host_id)
    assert host["reboot_required"]


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


def test_post_report_uebernimmt_security_updates_available(client):
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host()

    client.post(
        "/api/agent/report",
        json={
            "status": "ok",
            "summary": "keine Änderungen nötig",
            "details": {"updates_available": 5, "security_updates_available": 2},
        },
        headers=_auth(token),
    )

    host = hosts_store.get(host_id)
    assert host["updates_available"] == 5
    assert host["security_updates_available"] == 2


def test_post_report_ohne_security_feld_laesst_spalte_unangetastet(client):
    """apt-lose Hosts (Arch/pacman) schicken kein security_updates_available
    mit -- die Spalte muss dann bei ihrem Default (-1, "nicht anwendbar")
    bleiben statt faelschlich auf 0 zu fallen."""
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host()

    client.post(
        "/api/agent/report",
        json={"status": "ok", "summary": "keine Änderungen nötig", "details": {"updates_available": 3}},
        headers=_auth(token),
    )

    host = hosts_store.get(host_id)
    assert host["security_updates_available"] == -1


def test_post_report_benachrichtigt_bei_neuen_normalen_updates(client):
    _host_id, token = _create_host(updates_available=0)

    with patch("astrapi_core.modules.notify.engine._engine.send") as mock_send:
        client.post(
            "/api/agent/report",
            json={"status": "ok", "summary": "keine Änderungen nötig", "details": {"updates_available": 3}},
            headers=_auth(token),
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["event"] == "info"
    assert mock_send.call_args.kwargs["source"] == "hosts"


def test_post_report_benachrichtigt_als_warning_bei_security_updates(client):
    _host_id, token = _create_host(updates_available=0, security_updates_available=0)

    with patch("astrapi_core.modules.notify.engine._engine.send") as mock_send:
        client.post(
            "/api/agent/report",
            json={
                "status": "ok",
                "summary": "keine Änderungen nötig",
                "details": {"updates_available": 5, "security_updates_available": 2},
            },
            headers=_auth(token),
        )

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["event"] == "warning"


def test_post_report_keine_erneute_benachrichtigung_bei_gleicher_anzahl(client):
    """Sonst wuerde bei jedem 15-Minuten-Zyklus dieselbe unveraenderte
    Zahl erneut gemeldet."""
    _host_id, token = _create_host(updates_available=3)

    with patch("astrapi_core.modules.notify.engine._engine.send") as mock_send:
        client.post(
            "/api/agent/report",
            json={"status": "ok", "summary": "keine Änderungen nötig", "details": {"updates_available": 3}},
            headers=_auth(token),
        )

    mock_send.assert_not_called()


def test_proxmox_pending_updates_listet_nur_hosts_mit_pending_action(client):
    """E-010: von astrapi-backup genutzt, um kein Backup zu starten,
    waehrend hier ein Update laeuft -- bewusst unauthentifiziert."""
    _create_host(hostname="lxc-a", pending_action="update", proxmox_vmid=105)
    _create_host(hostname="lxc-b", pending_action="", proxmox_vmid=106)
    _create_host(hostname="lxc-c", pending_action="update", proxmox_vmid=-1)

    r = client.get("/api/agent/proxmox-pending-updates")

    assert r.status_code == 200
    assert r.json()["vmids"] == [105]


def test_proxmox_pending_updates_leer_ohne_treffer(client):
    r = client.get("/api/agent/proxmox-pending-updates")
    assert r.json()["vmids"] == []


def test_post_report_uebernimmt_paketlisten(client):
    """T-284-ADMIN: die konkreten Paketnamen (nicht nur die Anzahl)
    werden gespeichert -- Grundlage fuer die Vorschau vor 'Update
    anstoßen'."""
    from astrapi_admin.modules.hosts.ui.crud import store as hosts_store

    host_id, token = _create_host()

    client.post(
        "/api/agent/report",
        json={
            "status": "ok",
            "summary": "keine Änderungen nötig",
            "details": {
                "updates_available": 2,
                "upgradable_packages": ["htop", "libssl3"],
                "security_updates_available": 1,
                "security_upgradable_packages": ["libssl3"],
            },
        },
        headers=_auth(token),
    )

    host = hosts_store.get(host_id)
    assert host["updates_package_list"] == ["htop", "libssl3"]
    assert host["security_updates_package_list"] == ["libssl3"]


def test_post_report_mit_update_result_haengt_paketliste_ans_log(client):
    """T-284-ADMIN: nach einem Update soll im Log sichtbar sein, WAS
    aktualisiert wurde."""
    host_id, token = _create_host(pending_action="update")

    with patch("astrapi_core.system.activity_log.append_log_line") as mock_append:
        client.post(
            "/api/agent/report",
            json={
                "status": "ok",
                "summary": "aktualisiert",
                "details": {
                    "updates_available": 0,
                    "upgradable_packages": [],
                    "update_result": {"ok": True, "detail": "Setting up htop ...\ndone.", "packages": ["htop"]},
                },
            },
            headers=_auth(token),
        )

    lines = [c.args[1] for c in mock_append.call_args_list]
    assert any("htop" in ln and "Aktualisierte Pakete" in ln for ln in lines)
    assert "Setting up htop ..." in lines
    assert "done." in lines


def test_post_report_update_result_ohne_pakete_meldet_das_explizit(client):
    host_id, token = _create_host(pending_action="update")

    with patch("astrapi_core.system.activity_log.append_log_line") as mock_append:
        client.post(
            "/api/agent/report",
            json={
                "status": "error",
                "summary": "Update fehlgeschlagen",
                "details": {
                    "updates_available": 3,
                    "update_result": {"ok": False, "detail": "network error", "packages": []},
                },
            },
            headers=_auth(token),
        )

    lines = [c.args[1] for c in mock_append.call_args_list]
    assert any("keine Pakete betroffen" in ln for ln in lines)


def test_post_report_ohne_update_versuch_haengt_trotzdem_eine_zeile_an(client):
    """Nachtrag zu T-306-ADMIN: der "Log anzeigen"-Dialog zeigt nur
    angehaengte Zeilen, nie das description-Feld des activity_log-
    Eintrags selbst -- ein normaler Drift/OK/Konflikt-Report OHNE
    Update-Versuch haengte bisher gar keine Zeile an und der Dialog
    blieb faelschlich leer."""
    host_id, token = _create_host()

    with patch("astrapi_core.system.activity_log.append_log_line") as mock_append:
        client.post(
            "/api/agent/report",
            json={"status": "ok", "summary": "keine Änderungen nötig", "details": {}},
            headers=_auth(token),
        )

    mock_append.assert_called()
    lines = [c.args[1] for c in mock_append.call_args_list]
    assert any("keine Änderungen nötig" in ln for ln in lines)


def test_post_report_drift_bekommt_warning_praefix_und_detailzeile(client):
    host_id, token = _create_host()

    with patch("astrapi_core.system.activity_log.append_log_line") as mock_append:
        client.post(
            "/api/agent/report",
            json={
                "status": "drift",
                "summary": "1 übersprungen (Fremdbesitz)",
                "details": {
                    "config_files": [
                        {
                            "path": "/etc/apt/sources.list.d/simpsons.sources",
                            "action": "absent",
                            "status": "skipped_conflict",
                            "detail": "wurde nicht von astrapi-admin angelegt -- nicht gelöscht",
                        }
                    ]
                },
            },
            headers=_auth(token),
        )

    lines = [c.args[1] for c in mock_append.call_args_list]
    assert any(ln.startswith("WARNING: 1 übersprungen") for ln in lines)
    assert any(
        ln == "WARNING: /etc/apt/sources.list.d/simpsons.sources: "
        "wurde nicht von astrapi-admin angelegt -- nicht gelöscht"
        for ln in lines
    )


def test_post_report_fehlgeschlagenes_paket_bekommt_error_praefix(client):
    host_id, token = _create_host()

    with patch("astrapi_core.system.activity_log.append_log_line") as mock_append:
        client.post(
            "/api/agent/report",
            json={
                "status": "error",
                "summary": "1 fehlgeschlagen",
                "details": {
                    "packages": [{"name": "caddy", "status": "failed", "detail": "caddy ist nicht installiert"}]
                },
            },
            headers=_auth(token),
        )

    lines = [c.args[1] for c in mock_append.call_args_list]
    assert any(ln.startswith("ERROR: 1 fehlgeschlagen") for ln in lines)
    assert any(ln == "ERROR: caddy: caddy ist nicht installiert" for ln in lines)


def test_post_report_ok_items_werden_nicht_als_detailzeile_geloggt(client):
    host_id, token = _create_host()

    with patch("astrapi_core.system.activity_log.append_log_line") as mock_append:
        client.post(
            "/api/agent/report",
            json={
                "status": "ok",
                "summary": "keine Änderungen nötig",
                "details": {"packages": [{"name": "vim", "status": "ok"}]},
            },
            headers=_auth(token),
        )

    lines = [c.args[1] for c in mock_append.call_args_list]
    assert not any("vim" in ln for ln in lines)
    assert len(lines) == 1

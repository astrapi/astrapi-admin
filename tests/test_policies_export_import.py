"""policies/ui/__init__.py::policies_export()/policies_import_preview() --
T-290-ADMIN: Policy als JSON exportieren (z.B. vom Testserver), auf einem
anderen Server importieren. Export enthaelt nie Klartext-Geheimnisse (die
liegen im Storage fuer secret=true-Eintraege ohnehin nie im 'content'-Feld,
siehe engine.secret_name()); der Import legt NICHTS direkt an, sondern
uebergibt das geparste JSON an den bestehenden Edit-Dialog zur Pruefung
vor dem eigentlichen Anlegen (policies_create())."""
import asyncio
import json
from unittest.mock import patch

import pytest
from astrapi_core.system import db, secrets
from starlette.datastructures import FormData

from astrapi_admin.modules.policies import engine as policies_engine
from astrapi_admin.modules.policies.ui import _slug, policies_export, policies_import_preview


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    secrets._key_path_prod = None
    secrets._key_path_dev = None
    secrets.configure(key_path=tmp_path / ".secret.key")
    yield


class _FakeRequest:
    def __init__(self, items: list[tuple[str, str]]):
        self._form = FormData(items)

    async def form(self):
        return self._form


def _run(coro):
    return asyncio.run(coro)


def _create_policy(policy_id="p1", **overrides) -> dict:
    values = {
        "name": "caddy",
        "description": "Reverse-Proxy",
        "enabled": True,
        "packages_arch": ["caddy"],
        "packages_debian": ["caddy"],
        "config_files": [
            {
                "path": "/etc/caddy/Caddyfile",
                "action": "enforce",
                "content": ":443 { }",
                "mode": "0644",
                "owner": "caddy",
                "group": "caddy",
                "force": False,
                "secret": False,
            }
        ],
        "services": [{"name": "caddy", "state": "enabled_started"}],
    }
    values.update(overrides)
    policies_engine.create_policy(policy_id, values)
    return values


# ── Export ───────────────────────────────────────────────────────────────


def test_slug_macht_einen_dateinamen_tauglichen_kurznamen():
    assert _slug("Caddy Reverse-Proxy!") == "caddy-reverse-proxy"
    assert _slug("") == "policy"
    assert _slug(None) == "policy"


def test_export_liefert_json_mit_den_gespeicherten_feldern():
    _create_policy("p1")

    response = policies_export("p1")

    body = json.loads(response.body)
    assert body["name"] == "caddy"
    assert body["config_files"][0]["path"] == "/etc/caddy/Caddyfile"
    assert response.media_type == "application/json"
    assert 'filename="policy-caddy.json"' in response.headers["content-disposition"]


def test_export_unbekannte_policy_gibt_404():
    response = policies_export("does-not-exist")

    assert response.status_code == 404


def test_export_enthaelt_nie_das_geheimnis_im_klartext():
    _create_policy(
        "p-secret",
        config_files=[
            {
                "path": "/etc/caddy/wildcard.key",
                "action": "enforce",
                "content": "",
                "mode": "0600",
                "owner": "caddy",
                "group": "caddy",
                "force": False,
                "secret": True,
            }
        ],
    )
    secrets.set_secret(policies_engine.secret_name("p-secret", "/etc/caddy/wildcard.key"), "der-echte-key")

    response = policies_export("p-secret")

    assert b"der-echte-key" not in response.body
    body = json.loads(response.body)
    assert body["config_files"][0]["secret"] is True
    assert body["config_files"][0]["content"] == ""


# ── Import-Preview ───────────────────────────────────────────────────────


def test_import_preview_parst_gueltiges_json_und_zeigt_edit_dialog():
    payload = json.dumps({"name": "imported-caddy", "config_files": [], "services": []})

    with patch("astrapi_admin.modules.policies.ui.render") as mock_render:
        _run(policies_import_preview(_FakeRequest([("import_json", payload)])))

    template = mock_render.call_args[0][1]
    ctx = mock_render.call_args[0][2]
    assert template == "policies/dialogs/edit/modal.html"
    assert ctx["policy"]["id"] is None
    assert ctx["policy"]["name"] == "imported-caddy"
    assert ctx["error"] is None


def test_import_preview_ungueltiges_json_zeigt_fehler_im_import_dialog():
    with patch("astrapi_admin.modules.policies.ui.render") as mock_render:
        _run(policies_import_preview(_FakeRequest([("import_json", "{das ist kein json")])))

    template = mock_render.call_args[0][1]
    ctx = mock_render.call_args[0][2]
    assert template == "policies/dialogs/import/modal.html"
    assert "Kein gültiges JSON" in ctx["error"]
    assert ctx["raw"] == "{das ist kein json"
    assert mock_render.call_args.kwargs["status_code"] == 422


def test_import_preview_ohne_name_feld_zeigt_fehler():
    payload = json.dumps({"description": "ohne Name"})

    with patch("astrapi_admin.modules.policies.ui.render") as mock_render:
        _run(policies_import_preview(_FakeRequest([("import_json", payload)])))

    ctx = mock_render.call_args[0][2]
    assert "name" in ctx["error"]


def test_import_preview_ignoriert_fremde_felder_wie_eine_mitgelieferte_id():
    payload = json.dumps({"id": "fremde-id", "name": "x"})

    with patch("astrapi_admin.modules.policies.ui.render") as mock_render:
        _run(policies_import_preview(_FakeRequest([("import_json", payload)])))

    ctx = mock_render.call_args[0][2]
    assert ctx["policy"]["id"] is None


def test_import_preview_nicht_listen_felder_werden_zu_leeren_listen():
    payload = json.dumps({"name": "x", "config_files": "nicht-liste", "services": 123})

    with patch("astrapi_admin.modules.policies.ui.render") as mock_render:
        _run(policies_import_preview(_FakeRequest([("import_json", payload)])))

    ctx = mock_render.call_args[0][2]
    assert ctx["policy"]["config_files"] == []
    assert ctx["policy"]["services"] == []

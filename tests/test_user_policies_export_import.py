"""user_policies/ui/__init__.py::user_policies_export()/
user_policies_import_preview() -- analog zu test_policies_export_import.py
(T-290-ADMIN), hier für das Nutzer-Modul (astrapi-hub-Vault E-013-Folge:
claude-deploy über mehrere Dev-Hosts hinweg als Vorlage exportierbar
machen). SSH-Keys sind öffentliche Schlüssel, keine Geheimnisse -- anders
als bei Policies ist hier keine Secret-Ausklammerung nötig."""
import asyncio
import json
from unittest.mock import patch

import pytest
from astrapi_core.system import db
from starlette.datastructures import FormData

from astrapi_admin.modules.user_policies import engine as up_engine
from astrapi_admin.modules.user_policies.ui import _slug, user_policies_export, user_policies_import_preview


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
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
        "name": "claude-deploy",
        "description": "Deploy-Zugriff",
        "enabled": True,
        "entries": [
            {
                "username": "claude-deploy",
                "action": "enforce",
                "shell": "/bin/bash",
                "sudo": False,
                "ssh_keys": ["ssh-ed25519 AAAA... astrapi-hub-deploy-claude"],
            }
        ],
    }
    values.update(overrides)
    up_engine.create_user_policy(policy_id, values)
    return values


# ── Export ───────────────────────────────────────────────────────────────


def test_slug_macht_einen_dateinamen_tauglichen_kurznamen():
    assert _slug("claude deploy!") == "claude-deploy"
    assert _slug("") == "user-policy"
    assert _slug(None) == "user-policy"


def test_export_liefert_json_mit_den_gespeicherten_feldern():
    _create_policy("p1")

    response = user_policies_export("p1")

    body = json.loads(response.body)
    assert body["name"] == "claude-deploy"
    assert body["entries"][0]["username"] == "claude-deploy"
    assert response.media_type == "application/json"
    assert 'filename="user-policy-claude-deploy.json"' in response.headers["content-disposition"]


def test_export_unbekannte_policy_gibt_404():
    response = user_policies_export("does-not-exist")

    assert response.status_code == 404


def test_export_enthaelt_die_oeffentlichen_ssh_keys_im_klartext():
    """Anders als bei Policies (Klartext-Geheimnisse nie im Export, siehe
    test_policies_export_import.py) sind SSH-Public-Keys nicht schützenswert
    -- der Export soll sie 1:1 enthalten, damit der Import direkt
    funktioniert."""
    _create_policy("p1")

    response = user_policies_export("p1")

    assert b"astrapi-hub-deploy-claude" in response.body


# ── Import-Preview ───────────────────────────────────────────────────────


def test_import_preview_parst_gueltiges_json_und_zeigt_edit_dialog():
    payload = json.dumps({"name": "imported", "entries": []})

    with patch("astrapi_admin.modules.user_policies.ui.render") as mock_render:
        _run(user_policies_import_preview(_FakeRequest([("import_json", payload)])))

    template = mock_render.call_args[0][1]
    ctx = mock_render.call_args[0][2]
    assert template == "user_policies/dialogs/edit/modal.html"
    assert ctx["policy"]["id"] is None
    assert ctx["policy"]["name"] == "imported"
    assert ctx["error"] is None


def test_import_preview_ungueltiges_json_zeigt_fehler_im_import_dialog():
    with patch("astrapi_admin.modules.user_policies.ui.render") as mock_render:
        _run(user_policies_import_preview(_FakeRequest([("import_json", "{das ist kein json")])))

    template = mock_render.call_args[0][1]
    ctx = mock_render.call_args[0][2]
    assert template == "user_policies/dialogs/import/modal.html"
    assert "Kein gültiges JSON" in ctx["error"]
    assert ctx["raw"] == "{das ist kein json"
    assert mock_render.call_args.kwargs["status_code"] == 422


def test_import_preview_ohne_name_feld_zeigt_fehler():
    payload = json.dumps({"description": "ohne Name"})

    with patch("astrapi_admin.modules.user_policies.ui.render") as mock_render:
        _run(user_policies_import_preview(_FakeRequest([("import_json", payload)])))

    ctx = mock_render.call_args[0][2]
    assert "name" in ctx["error"]


def test_import_preview_ignoriert_fremde_felder_wie_eine_mitgelieferte_id():
    payload = json.dumps({"id": "fremde-id", "name": "x", "entries": []})

    with patch("astrapi_admin.modules.user_policies.ui.render") as mock_render:
        _run(user_policies_import_preview(_FakeRequest([("import_json", payload)])))

    ctx = mock_render.call_args[0][2]
    assert ctx["policy"]["id"] is None


def test_import_preview_nicht_listen_feld_entries_wird_zu_leerer_liste():
    payload = json.dumps({"name": "x", "entries": "nicht-liste"})

    with patch("astrapi_admin.modules.user_policies.ui.render") as mock_render:
        _run(user_policies_import_preview(_FakeRequest([("import_json", payload)])))

    ctx = mock_render.call_args[0][2]
    assert ctx["policy"]["entries"] == []


def test_import_preview_uebernimmt_entries_aus_dem_json():
    entries = [{"username": "claude-deploy", "action": "enforce", "shell": "/bin/bash", "sudo": False, "ssh_keys": []}]
    payload = json.dumps({"name": "x", "entries": entries})

    with patch("astrapi_admin.modules.user_policies.ui.render") as mock_render:
        _run(user_policies_import_preview(_FakeRequest([("import_json", payload)])))

    ctx = mock_render.call_args[0][2]
    assert ctx["policy"]["entries"] == entries

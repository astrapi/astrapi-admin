"""host_groups/ui/crud.py::host_groups_export()/host_groups_import_preview()
-- analog zu test_policies_export_import.py (T-290-ADMIN), hier für das
schema-getriebene Gruppen-Modul nachgebaut (astrapi-hub-Vault E-013-Folge).
Anders als bei Policies/Nutzer-Policies hat der generische crud_blueprint-
Router keinen eigenen Edit-Dialog -- die Import-Vorschau rendert deshalb
denselben generischen create_edit_modal.html-Dialog wie "Neu", nur mit
vorbefüllten Werten."""
import asyncio
import json
from unittest.mock import patch

import pytest
from astrapi_core.system import db
from starlette.datastructures import FormData

from astrapi_admin.modules.host_groups.ui.crud import (
    _slug,
    host_groups_export,
    host_groups_import_preview,
    store,
)


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


def _create_group(**overrides) -> tuple[str, dict]:
    """Gibt (id, values) zurück -- SqliteTableStore.create() ignoriert eine
    mitgegebene ID und vergibt immer eine neue per Auto-Increment."""
    values = {
        "name": "dev-hosts",
        "description": "Dev-LXCs",
        "policy_ids": ["p1"],
        "user_policy_ids": ["up1"],
        "mirror_repos": [],
        "enabled": True,
    }
    values.update(overrides)
    gid = store.create(None, values)
    return gid, values


# ── Export ───────────────────────────────────────────────────────────────


def test_slug_macht_einen_dateinamen_tauglichen_kurznamen():
    assert _slug("Dev Hosts!") == "dev-hosts"
    assert _slug("") == "gruppe"
    assert _slug(None) == "gruppe"


def test_export_liefert_json_mit_den_gespeicherten_feldern():
    gid, _ = _create_group()

    response = host_groups_export(gid)

    body = json.loads(response.body)
    assert body["name"] == "dev-hosts"
    assert body["policy_ids"] == ["p1"]
    assert body["user_policy_ids"] == ["up1"]
    assert response.media_type == "application/json"
    assert 'filename="host-group-dev-hosts.json"' in response.headers["content-disposition"]


def test_export_unbekannte_gruppe_gibt_404():
    response = host_groups_export("does-not-exist")

    assert response.status_code == 404


# ── Import-Preview ───────────────────────────────────────────────────────


def test_import_preview_parst_gueltiges_json_und_zeigt_generischen_edit_dialog():
    payload = json.dumps({"name": "imported-group", "policy_ids": ["p1"]})

    with patch("astrapi_admin.modules.host_groups.ui.crud.render") as mock_render:
        _run(host_groups_import_preview(_FakeRequest([("import_json", payload)])))

    template = mock_render.call_args[0][1]
    ctx = mock_render.call_args[0][2]
    assert template == "partials/create_edit/create_edit_modal.html"
    assert ctx["item_id"] is None
    assert ctx["item"]["name"] == "imported-group"
    assert ctx["item"]["policy_ids"] == ["p1"]
    assert ctx["submit_url"] == "/ui/host_groups/"
    assert ctx["method"] == "post"


def test_import_preview_ungueltiges_json_zeigt_fehler_im_import_dialog():
    with patch("astrapi_admin.modules.host_groups.ui.crud.render") as mock_render:
        _run(host_groups_import_preview(_FakeRequest([("import_json", "{das ist kein json")])))

    template = mock_render.call_args[0][1]
    ctx = mock_render.call_args[0][2]
    assert template == "host_groups/dialogs/import/modal.html"
    assert "Kein gültiges JSON" in ctx["error"]
    assert ctx["raw"] == "{das ist kein json"
    assert mock_render.call_args.kwargs["status_code"] == 422


def test_import_preview_ohne_name_feld_zeigt_fehler():
    payload = json.dumps({"description": "ohne Name"})

    with patch("astrapi_admin.modules.host_groups.ui.crud.render") as mock_render:
        _run(host_groups_import_preview(_FakeRequest([("import_json", payload)])))

    ctx = mock_render.call_args[0][2]
    assert "name" in ctx["error"]


def test_import_preview_nicht_listen_felder_werden_zu_leeren_listen():
    payload = json.dumps({"name": "x", "policy_ids": "nicht-liste", "user_policy_ids": 123})

    with patch("astrapi_admin.modules.host_groups.ui.crud.render") as mock_render:
        _run(host_groups_import_preview(_FakeRequest([("import_json", payload)])))

    ctx = mock_render.call_args[0][2]
    assert ctx["item"]["policy_ids"] == []
    assert ctx["item"]["user_policy_ids"] == []

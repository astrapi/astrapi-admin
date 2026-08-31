"""policies/ui/__init__.py::_parse_form() und policies/engine.py --
config_files[].secret: der Klartext landet nie im Policy-JSON, sondern
im Fernet-verschlüsselten Secrets-Store (astrapi_core.system.secrets),
adressiert über engine.secret_name(policy_id, path). Leer gelassen
behält den bestehenden Wert (wie ein Passwort-Feld)."""
import asyncio

import pytest
from astrapi_core.system import db, secrets
from starlette.datastructures import FormData

from astrapi_admin.modules.policies import engine as policies_engine
from astrapi_admin.modules.policies.ui import _parse_form


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


def _cf_form_items(policy_name="p", **cf) -> list[tuple[str, str]]:
    return [
        ("name", policy_name),
        ("description", ""),
        ("packages_arch", ""),
        ("packages_debian", ""),
        ("cf_path", cf.get("path", "/etc/caddy/wildcard.key")),
        ("cf_action", cf.get("action", "enforce")),
        ("cf_content", cf.get("content", "")),
        ("cf_mode", cf.get("mode", "0600")),
        ("cf_owner", cf.get("owner", "root")),
        ("cf_group", cf.get("group", "root")),
        ("cf_force", cf.get("force", "0")),
        ("cf_secret", cf.get("secret", "1")),
    ]


def test_parse_form_secret_zeile_speichert_content_nicht_im_json():
    data = _run(_parse_form(_FakeRequest(_cf_form_items(content="-----BEGIN KEY-----")), "p1"))

    cf = data["config_files"][0]
    assert cf["secret"] is True
    assert cf["content"] == ""


def test_parse_form_secret_zeile_speichert_wert_im_secrets_store():
    _run(_parse_form(_FakeRequest(_cf_form_items(content="geheim-123")), "p1"))

    stored = secrets.get_secret_safe(policies_engine.secret_name("p1", "/etc/caddy/wildcard.key"))
    assert stored == "geheim-123"


def test_parse_form_leerer_wert_behaelt_bestehendes_secret():
    _run(_parse_form(_FakeRequest(_cf_form_items(content="erster-wert")), "p1"))

    _run(_parse_form(_FakeRequest(_cf_form_items(content="")), "p1"))

    stored = secrets.get_secret_safe(policies_engine.secret_name("p1", "/etc/caddy/wildcard.key"))
    assert stored == "erster-wert"


def test_parse_form_nicht_leerer_wert_ueberschreibt_bestehendes_secret():
    _run(_parse_form(_FakeRequest(_cf_form_items(content="alt")), "p1"))

    _run(_parse_form(_FakeRequest(_cf_form_items(content="neu")), "p1"))

    stored = secrets.get_secret_safe(policies_engine.secret_name("p1", "/etc/caddy/wildcard.key"))
    assert stored == "neu"


def test_parse_form_normale_zeile_ohne_secret_flag_unveraendert():
    data = _run(
        _parse_form(
            _FakeRequest(_cf_form_items(path="/etc/caddy/Caddyfile", content="normal", secret="0")), "p1"
        )
    )

    cf = data["config_files"][0]
    assert cf["secret"] is False
    assert cf["content"] == "normal"


def test_resolve_policy_for_host_ersetzt_secret_inhalt(monkeypatch):
    policies_engine.create_policy(
        "p1",
        {
            "name": "wildcard",
            "enabled": True,
            "config_files": [
                {
                    "path": "/etc/caddy/wildcard.key",
                    "action": "enforce",
                    "content": "",
                    "mode": "0600",
                    "owner": "root",
                    "group": "root",
                    "force": False,
                    "secret": True,
                }
            ],
        },
    )
    secrets.set_secret(policies_engine.secret_name("p1", "/etc/caddy/wildcard.key"), "der-echte-key")
    host = {"os_type": "debian", "group_ids": [], "policy_ids": ["p1"]}

    result = policies_engine.resolve_policy_for_host(host)

    assert result["config_files"][0]["content"] == "der-echte-key"


def test_resolve_policy_for_host_fehlendes_secret_liefert_leeren_string():
    """Eigener policy_id ('p-ohne-secret' statt 'p1'), damit dieser Test
    nicht vom os.environ-Mirroring in secrets.set_secret() eines anderen
    Tests kollidiert -- set_secret() spiegelt den Wert zusaetzlich in
    os.environ[key], das ist NICHT Teil der DB-Isolationsfixture und
    ueberlebt zwischen Tests im selben Prozess."""
    policies_engine.create_policy(
        "p-ohne-secret",
        {
            "name": "wildcard",
            "enabled": True,
            "config_files": [
                {
                    "path": "/etc/caddy/wildcard.key",
                    "action": "enforce",
                    "content": "",
                    "mode": "0600",
                    "owner": "root",
                    "group": "root",
                    "force": False,
                    "secret": True,
                }
            ],
        },
    )
    host = {"os_type": "debian", "group_ids": [], "policy_ids": ["p-ohne-secret"]}

    result = policies_engine.resolve_policy_for_host(host)

    assert result["config_files"][0]["content"] == ""

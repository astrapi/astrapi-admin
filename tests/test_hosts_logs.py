"""hosts/ui/crud.py::get_logs()/get_log_by_id() -- T-284-ADMIN: der
generische 'type: log'-Card-Action aus astrapi-core (siehe modul.yaml),
zeigt die Activity-Log-Historie eines Hosts inkl. der von post_report()
angehaengten Update-Zeilen (siehe test_agent_api.py). Wie bei
test_trigger_update_dialog.py wird render() gemockt statt die volle
Jinja2-Umgebung zu konfigurieren -- reine Kontextpruefung."""
from unittest.mock import patch

import pytest
from astrapi_core.system import db

from astrapi_admin.modules.hosts.ui import crud as hosts_crud
from astrapi_admin.modules.hosts.ui.crud import store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _create_host(**overrides) -> str:
    values = {
        "hostname": "lxc99",
        "label": "lxc99",
        "os_type": "debian",
        "group_ids": [], "policy_ids": [],
        "token_hash": "x",
        "last_seen": "", "last_report": "", "last_status": "",
        "enabled": True,
    }
    values.update(overrides)
    return str(store.create(None, values))


def test_get_logs_ohne_eintraege():
    host_id = _create_host()

    with patch("astrapi_admin.modules.hosts.ui.crud.render") as mock_render:
        hosts_crud.get_logs(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["lines"] == []
    assert ctx["dates"] == []
    assert ctx["module"] == "hosts"


def test_get_logs_zeigt_aktuellsten_run_mit_seinen_zeilen():
    from astrapi_core.system.activity_log import append_log_line, log_activity

    host_id = _create_host()
    log_id = log_activity(
        log_type="job", module="hosts", item_id=host_id,
        description="aktualisiert", status="ok",
    )
    append_log_line(log_id, "Aktualisierte Pakete (1): htop")
    append_log_line(log_id, "Setting up htop ...")

    with patch("astrapi_admin.modules.hosts.ui.crud.render") as mock_render:
        hosts_crud.get_logs(host_id, request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["lines"] == ["Aktualisierte Pakete (1): htop", "Setting up htop ..."]
    assert ctx["selected"] == str(log_id)
    assert len(ctx["dates"]) == 1


def test_get_log_by_id_direkt():
    from astrapi_core.system.activity_log import append_log_line, log_activity

    host_id = _create_host()
    log_id = log_activity(
        log_type="job", module="hosts", item_id=host_id,
        description="aktualisiert", status="ok",
    )
    append_log_line(log_id, "Testzeile")

    with patch("astrapi_admin.modules.hosts.ui.crud.render") as mock_render:
        hosts_crud.get_log_by_id(host_id, str(log_id), request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["lines"] == ["Testzeile"]


def test_get_log_by_id_ungueltige_id_liefert_leere_liste():
    with patch("astrapi_admin.modules.hosts.ui.crud.render") as mock_render:
        hosts_crud.get_log_by_id("irrelevant", "keine-zahl", request=None)

    ctx = mock_render.call_args[0][2]
    assert ctx["lines"] == []

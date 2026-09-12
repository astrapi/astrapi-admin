"""modules/hosts/agent_settings.py::poll_interval_minutes() -- E-011:
type: number-Settings-Felder kommen aus settings_save_module() als
roher String zurueck (kein automatisches int()), muss hier defensiv
geparst und auf [1, 1440] geklemmt werden."""
from astrapi_admin.modules.hosts import agent_settings


def _patch_get_module(monkeypatch, value):
    monkeypatch.setattr(
        "astrapi_core.ui.settings_registry.get_module",
        lambda module_key, key, default=None: value,
    )


def test_poll_interval_minutes_default_ohne_gesetzten_wert(monkeypatch):
    _patch_get_module(monkeypatch, 15)

    assert agent_settings.poll_interval_minutes() == 15


def test_poll_interval_minutes_parst_string_aus_dem_settings_store(monkeypatch):
    _patch_get_module(monkeypatch, "60")

    assert agent_settings.poll_interval_minutes() == 60


def test_poll_interval_minutes_klemmt_zu_kleinen_wert(monkeypatch):
    _patch_get_module(monkeypatch, "0")

    assert agent_settings.poll_interval_minutes() == 1


def test_poll_interval_minutes_klemmt_zu_grossen_wert(monkeypatch):
    _patch_get_module(monkeypatch, "999999")

    assert agent_settings.poll_interval_minutes() == 1440


def test_poll_interval_minutes_faellt_bei_ungueltigem_wert_auf_default_zurueck(monkeypatch):
    _patch_get_module(monkeypatch, "kaputt")

    assert agent_settings.poll_interval_minutes() == 15


def test_timezone_default_ist_leer(monkeypatch):
    _patch_get_module(monkeypatch, "")

    assert agent_settings.timezone() == ""


def test_timezone_liefert_gesetzten_wert(monkeypatch):
    _patch_get_module(monkeypatch, "Europe/Berlin")

    assert agent_settings.timezone() == "Europe/Berlin"


def test_timezone_trimmt_whitespace(monkeypatch):
    _patch_get_module(monkeypatch, "  Europe/Berlin  ")

    assert agent_settings.timezone() == "Europe/Berlin"


def test_timezone_none_wird_zu_leerem_string(monkeypatch):
    _patch_get_module(monkeypatch, None)

    assert agent_settings.timezone() == ""

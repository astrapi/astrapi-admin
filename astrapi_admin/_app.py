"""astrapi_admin._app – ASGI-App-Factory.

Start:
    uvicorn astrapi_admin._app:app
    astrapi-admin --work-dir /opt/astrapi-admin --port 5005
"""

import time

from astrapi_core.system.paths import configure as _configure_paths

_configure_paths("astrapi-admin")

from astrapi_core.modules.settings.engine import configure as configure_settings
from astrapi_core.modules.system.engine import configure_updater
from astrapi_core.system.health import register_health
from astrapi_core.system.systemd import sd_notify, start_watchdog
from astrapi_core.system.version import get_display_name
from astrapi_core.ui import create as create_ui
from astrapi_core.ui.module_registry import load_modules
from astrapi_core.ui.settings_registry import init as settings_init
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from astrapi_admin._paths import db_path, package_dir, work_dir
from astrapi_admin.api.fastapi_app import create as create_api

_START_TIME = time.time()


def _db_check() -> tuple[bool, dict]:
    from astrapi_core.system.db import _conn

    try:
        _conn().execute("SELECT 1").fetchone()
        return True, {"db": True}
    except Exception:
        return False, {"db": False}


def _migrate_host_groups_user_policy_ids() -> None:
    """register_table()'s DDL ist CREATE TABLE IF NOT EXISTS -- legt bei
    bereits bestehender Tabelle keine neuen Spalten nach. user_policy_ids
    kam nachträglich zu host_groups dazu (Gruppen-Zuweisung für
    user_policies, astrapi-hub-Vault E-013-Folge), hier per ALTER TABLE
    ergänzt (gleiches Muster wie astrapi_sync/_app.py::
    _migrate_folders_storage_location())."""
    from astrapi_core.system.db import _conn

    con = _conn()
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(host_groups)")]
        if "user_policy_ids" not in cols:
            con.execute("ALTER TABLE host_groups ADD COLUMN user_policy_ids TEXT NOT NULL DEFAULT ''")
            con.commit()
    except Exception:
        pass


def create_app() -> FastAPI:
    _pkg = package_dir()
    configure_settings(health_fn=_db_check, app_name=get_display_name(_pkg))
    configure_updater(_pkg)

    from astrapi_core.system.db import configure as _configure_db
    from astrapi_core.system.db import create_all_registered_tables

    _configure_db(db_path())
    create_all_registered_tables()
    _migrate_host_groups_user_policy_ids()

    settings_init(work_dir())

    modules, _ = load_modules(_pkg)
    api = create_api(modules=modules)

    from pathlib import Path

    import astrapi_core.ui

    core_static = Path(astrapi_core.ui.__file__).parent / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")

    create_ui(api, app_root=_pkg, modules=modules)

    register_health(api, check_fn=_db_check, start_time=_START_TIME)
    start_watchdog(check_fn=lambda: _db_check()[0])
    sd_notify("READY=1")
    return api


app = create_app()

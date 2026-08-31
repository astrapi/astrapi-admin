from pathlib import Path

from astrapi_core.ui.controls import Header
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

from astrapi_admin.modules.templates.ui import api_router, templates_table  # noqa: E402
from astrapi_admin.modules.templates.ui import router as ui_router  # noqa: E402

module = load_modul(
    Path(__file__).parent,
    _KEY,
    api_router,
    ui_router,
    ui_header=Header(
        [
            Header.action_button(
                "Neue Vorlage",
                hx_get=f"/ui/{_KEY}/new",
                hx_target="body",
                style="primary",
                icon="plus",
            ),
        ]
    ),
    ui_content=templates_table,
)

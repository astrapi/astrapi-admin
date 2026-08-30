"""astrapi_admin.api.fastapi_app – FastAPI-Factory."""
from fastapi import FastAPI
from astrapi_core.system.version import get_app_version

from astrapi_admin._paths import package_dir

APP_ROOT = package_dir()


def create(modules: list | None = None) -> FastAPI:
    _version = get_app_version(APP_ROOT, default="0.0.1")
    app = FastAPI(
        title="astrapi-admin API",
        version=_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    from astrapi_core.ui.module_registry import load_modules, register_fastapi_modules
    if modules is None:
        modules, _ = load_modules(APP_ROOT)
    register_fastapi_modules(app, modules)

    from astrapi_admin.api.agent import router as agent_router
    app.include_router(agent_router)

    return app

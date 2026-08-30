# astrapi_admin/_paths.py
from pathlib import Path

from astrapi_core.system.paths import db_path, log_dir, work_dir  # noqa: F401 – re-export


def package_dir() -> Path:
    """Pfad zum installierten Package – für app.yaml, Templates, Modul-YAMLs."""
    return Path(__file__).resolve().parent

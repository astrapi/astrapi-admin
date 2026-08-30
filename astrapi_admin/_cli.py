"""astrapi_admin._cli – Console-Script-Einstiegspunkt.

Start:
    astrapi-admin --work-dir /opt/astrapi-admin --port 5005
    astrapi-admin --work-dir /opt/astrapi-admin --port 5005 --debug
"""
from astrapi_core.system.paths import run_app


def main() -> None:
    run_app("astrapi_admin._app:app", "astrapi-admin", default_port=5005)


if __name__ == "__main__":
    main()

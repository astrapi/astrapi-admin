# astrapi_admin/modules/templates/engine.py
"""GPO-artige Vorlagen: Pakete + parametrisierte Config-Dateien + Formular
(siehe [[E-003]]-Folgeplan, "Templates"-Idee des Nutzers). Speicherung wie
policies (SqliteStorage), Rendering ausschliesslich serverseitig -- der
Agent bekommt wie jede andere Policy nur fertig aufgeloesten Text, keine
neue Abhaengigkeit im Agent-Repo noetig.

SandboxedEnvironment + StrictUndefined statt der Jinja2-Defaults: ein
Tippfehler im Template, der auf einen nicht existierenden Parameter
verweist, muss laut fehlschlagen statt eine leere Zeile in eine echte
Config-Datei auf einem echten Host zu schreiben (gleiches Prinzip wie die
in dieser Session behobenen Robustheitslücken in
astrapi_admin_agent/files.py -- hier von Anfang an eingebaut)."""
from astrapi_core.ui.storage import SqliteStorage
from jinja2 import StrictUndefined, UndefinedError
from jinja2.sandbox import SandboxedEnvironment, SecurityError

_jinja_env = SandboxedEnvironment(undefined=StrictUndefined)


def _store() -> SqliteStorage:
    return SqliteStorage("templates")


def list_templates() -> dict:
    return _store().list()


def get_template(template_id: str) -> dict | None:
    return _store().get(template_id)


def create_template(template_id: str, values: dict) -> str:
    return _store().create(template_id, values)


def update_template(template_id: str, values: dict) -> None:
    _store().update(template_id, values)


def delete_template(template_id: str) -> None:
    _store().delete(template_id)


def toggle_template(template_id: str) -> None:
    _store().toggle(template_id)


def templates_for_select() -> list[dict]:
    return [{"value": tid, "label": t.get("name") or tid} for tid, t in _store().list().items()]


class TemplateRenderError(Exception):
    """Aufloesbarer Fehler beim Rendern eines Templates -- wird von
    policies/engine.py::resolve_policy_for_host() abgefangen und bricht
    dort NICHT die Aufloesung fuer andere Policies/Hosts."""


def render_template(template_id: str, params: dict | None) -> dict:
    """Rendert ein Template mit konkreten Parameterwerten.

    Gibt bei Erfolg {"packages_arch", "packages_debian", "config_files",
    "services"} zurueck -- identische Form wie eine rohe Policy, damit
    resolve_policy_for_host() sie unveraendert weiterverarbeiten kann.
    Wirft TemplateRenderError bei fehlendem/deaktiviertem Template,
    fehlendem Pflichtparameter oder einem Jinja2-Fehler.
    """
    tpl = get_template(template_id)
    if tpl is None or not tpl.get("enabled", True):
        raise TemplateRenderError(f"Vorlage '{template_id}' nicht gefunden oder deaktiviert")

    params = params or {}
    values: dict = {}
    missing: list[str] = []
    for pd in tpl.get("params") or []:
        key = pd.get("key")
        if not key:
            continue
        supplied = params.get(key)
        if supplied not in (None, ""):
            values[key] = supplied
        elif pd.get("default") is not None:
            values[key] = pd["default"]
        elif pd.get("required"):
            missing.append(key)
    if missing:
        raise TemplateRenderError(f"Fehlender Pflichtparameter: {', '.join(missing)}")

    def _render(text: str) -> str:
        try:
            return _jinja_env.from_string(text or "").render(**values)
        except (UndefinedError, SecurityError) as e:
            raise TemplateRenderError(f"Fehler beim Rendern von '{template_id}': {e}") from e

    config_files = []
    for cf in tpl.get("config_files") or []:
        cf = dict(cf)
        if cf.get("action", "enforce") != "absent":
            cf["content"] = _render(cf.get("content", ""))
        config_files.append(cf)

    return {
        "packages_arch": tpl.get("packages_arch") or {"present": [], "absent": []},
        "packages_debian": tpl.get("packages_debian") or {"present": [], "absent": []},
        "config_files": config_files,
        "services": tpl.get("services") or [],
    }

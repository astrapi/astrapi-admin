"""templates/engine.py::render_template() -- Kernstück der GPO-artigen
Vorlagen. Fokus auf Robustheit: ein Tippfehler im Platzhalter oder ein
fehlender Pflichtparameter darf nicht still eine kaputte Config-Datei
erzeugen, sondern muss klar fehlschlagen (StrictUndefined + explizite
Pflichtparameter-Prüfung), und ein böswilliger/fehlerhafter Template-
Ausdruck darf nicht mehr als reines Text-Rendering können
(SandboxedEnvironment)."""
import pytest
from astrapi_core.system import db

from astrapi_admin.modules.templates import engine as templates_engine


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


def _tpl(**overrides):
    base = {
        "name": "Caddy",
        "enabled": True,
        "packages_arch": {"present": ["caddy"], "absent": []},
        "packages_debian": {"present": ["caddy"], "absent": []},
        "services": [{"name": "caddy", "state": "enabled_started"}],
        "config_files": [
            {
                "path": "/etc/caddy/Caddyfile",
                "action": "enforce",
                "content": "{{ domain }} {\n    reverse_proxy {{ upstream }}\n}\n",
                "mode": "0644",
                "owner": "root",
                "group": "root",
            }
        ],
        "params": [
            {"key": "domain", "label": "Domain", "default": None, "required": True},
            {"key": "upstream", "label": "Upstream", "default": "127.0.0.1:8080", "required": False},
        ],
    }
    base.update(overrides)
    return base


def test_render_template_erfolg():
    templates_engine.create_template("caddy", _tpl())
    result = templates_engine.render_template("caddy", {"domain": "example.org"})

    assert result["packages_arch"] == {"present": ["caddy"], "absent": []}
    content = result["config_files"][0]["content"]
    assert "example.org {" in content
    assert "reverse_proxy 127.0.0.1:8080" in content  # Default genutzt


def test_render_template_expliziter_wert_ueberschreibt_default():
    templates_engine.create_template("caddy", _tpl())
    result = templates_engine.render_template("caddy", {"domain": "x.org", "upstream": "10.0.0.5:9000"})
    assert "reverse_proxy 10.0.0.5:9000" in result["config_files"][0]["content"]


def test_render_template_fehlender_pflichtparameter_wirft_klaren_fehler():
    templates_engine.create_template("caddy", _tpl())
    with pytest.raises(templates_engine.TemplateRenderError, match="domain"):
        templates_engine.render_template("caddy", {})


def test_render_template_tippfehler_im_platzhalter_wirft_fehler_statt_leerer_ausgabe():
    """StrictUndefined: ein Platzhalter, der auf keinen deklarierten
    Parameter verweist, darf nicht als leerer String durchrutschen."""
    tpl = _tpl()
    tpl["config_files"][0]["content"] = "{{ domain }} { reverse_proxy {{ upstrea }} }"  # Tippfehler
    templates_engine.create_template("caddy", tpl)
    with pytest.raises(templates_engine.TemplateRenderError):
        templates_engine.render_template("caddy", {"domain": "example.org", "upstream": "x:1"})


def test_render_template_unbekanntes_template_wirft_fehler():
    with pytest.raises(templates_engine.TemplateRenderError):
        templates_engine.render_template("nicht-vorhanden", {})


def test_render_template_deaktiviertes_template_wirft_fehler():
    templates_engine.create_template("caddy", _tpl(enabled=False))
    with pytest.raises(templates_engine.TemplateRenderError):
        templates_engine.render_template("caddy", {"domain": "x.org"})


def test_render_template_action_absent_wird_nicht_gerendert():
    """Eine 'absent'-Config-Datei braucht keinen Inhalt (wird ohnehin nur
    gelöscht) -- darf also auch nicht an fehlenden Parametern scheitern."""
    tpl = _tpl(
        config_files=[
            {"path": "/etc/old.conf", "action": "absent", "content": "{{ nie_gesetzt }}"},
        ],
        params=[],
    )
    templates_engine.create_template("caddy", tpl)
    result = templates_engine.render_template("caddy", {})
    assert result["config_files"][0]["content"] == "{{ nie_gesetzt }}"


def test_render_template_sandbox_blockiert_gefaehrlichen_ausdruck():
    """SandboxedEnvironment: ein Ausdruck, der versucht auf Python-Internas
    zuzugreifen (klassischer Jinja2-SSTI-Trick), muss abgelehnt werden --
    Verteidigung in der Tiefe, auch wenn Templates hier nur vom
    Betreiber selbst stammen."""
    tpl = _tpl(
        config_files=[
            {
                "path": "/etc/x.conf",
                "action": "enforce",
                "content": "{{ ''.__class__.__mro__[1].__subclasses__() }}",
            }
        ],
        params=[],
    )
    templates_engine.create_template("caddy", tpl)
    with pytest.raises(templates_engine.TemplateRenderError):
        templates_engine.render_template("caddy", {})

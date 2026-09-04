"""policies/ui/__init__.py::_list_item() -- T-288-ADMIN: list_wrapper_inner.html
rendert die NAME-Spalte immer fest aus item_data.description. Policies
haben aber ein eigenes 'name'-Feld (Pflicht beim Anlegen) UND ein
separates, optionales 'description'-Feld -- ohne Auflösung zeigte die
NAME-Spalte je nach Fall die rohe Policy-ID oder faelschlich den
Beschreibungstext statt des Namens."""
from astrapi_admin.modules.policies.ui import _list_item


def test_list_item_zeigt_namen_als_description_fuer_die_name_spalte():
    p = {"name": "caddy", "description": "Domain-loser Reverse-Proxy"}
    result = _list_item("e94530f229b4", p)
    assert result["description"] == "caddy"


def test_list_item_behaelt_echten_beschreibungstext_separat():
    p = {"name": "caddy", "description": "Domain-loser Reverse-Proxy"}
    result = _list_item("e94530f229b4", p)
    assert result["description_text"] == "Domain-loser Reverse-Proxy"


def test_list_item_ohne_beschreibung_zeigt_platzhalter():
    p = {"name": "testfile", "description": ""}
    result = _list_item("aa63c5222b0e", p)
    assert result["description_text"] == "—"


def test_list_item_ohne_namen_faellt_auf_policy_id_zurueck():
    """Sollte eigentlich nie vorkommen (name ist beim Anlegen Pflicht),
    aber besser eine erkennbare ID zeigen als eine leere Zelle."""
    p = {"name": "", "description": ""}
    result = _list_item("76ed03facd77", p)
    assert result["description"] == "76ed03facd77"


def test_list_item_zeigt_zuweisung_host_ohne_group_only():
    """T-305-ADMIN: Col.badge_enum() rendert einen falsy-Wert (Python
    False) nie ueber die values-Map, egal was fuer ein 'False'-Eintrag
    dort steht (siehe ui_macros.html::col_cell) -- group_only muss
    deshalb auf einen eigenen, immer truthy-String umgeschrieben werden,
    damit "Host" statt einer leeren Zelle erscheint."""
    p = {"name": "caddy", "group_only": False}
    result = _list_item("e94530f229b4", p)
    assert result["group_only"] == "Host"


def test_list_item_zeigt_zuweisung_gruppe_mit_group_only():
    p = {"name": "caddy", "group_only": True}
    result = _list_item("e94530f229b4", p)
    assert result["group_only"] == "Gruppe"

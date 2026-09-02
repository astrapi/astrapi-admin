"""user_policies/ui/__init__.py::_list_item() -- dieselbe NAME-Spalten-
Kollision wie bei policies (T-288-ADMIN)/host_groups (T-291-ADMIN):
list_wrapper_inner.html rendert die NAME-Spalte immer fest aus
item_data.description. user_policies hat wie policies ein eigenes
'name'-Feld UND ein separates 'description'-Feld -- hier von Anfang an
kollisionsfrei aufgelöst statt erst nachträglich gefixt."""
from astrapi_admin.modules.user_policies.ui import _list_item, _summary


def test_list_item_zeigt_namen_als_description_fuer_die_name_spalte():
    p = {"name": "base-admins", "description": "Admin-Zugänge für alle Server", "entries": []}
    result = _list_item("abc123", p)
    assert result["description"] == "base-admins"


def test_list_item_behaelt_echten_beschreibungstext_separat():
    p = {"name": "base-admins", "description": "Admin-Zugänge für alle Server", "entries": []}
    result = _list_item("abc123", p)
    assert result["description_text"] == "Admin-Zugänge für alle Server"


def test_list_item_ohne_beschreibung_zeigt_platzhalter():
    p = {"name": "base-admins", "description": "", "entries": []}
    result = _list_item("abc123", p)
    assert result["description_text"] == "—"


def test_list_item_ohne_namen_faellt_auf_policy_id_zurueck():
    p = {"name": "", "description": "", "entries": []}
    result = _list_item("abc123", p)
    assert result["description"] == "abc123"


def test_summary_zeigt_anzahl_nutzer():
    assert _summary({"entries": [{"username": "alice"}]}) == "1 Nutzer"
    assert _summary({"entries": [{"username": "alice"}, {"username": "bob"}]}) == "2 Nutzer"


def test_summary_ohne_eintraege_zeigt_leer():
    assert _summary({"entries": []}) == "leer"
    assert _summary({}) == "leer"

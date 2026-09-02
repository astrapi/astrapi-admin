# astrapi_admin/modules/user_policies/engine.py
"""Nutzer-Policy-Speicherung (SqliteStorage, wie modules/policies/engine.py)
und Aufloesung fuer einen Host.

E-012: eigenes Modul statt Erweiterung der allgemeinen Policies --
Zugriffsverwaltung ist sicherheitskritischer als App-Config und verdient
eine eigene, klar abgegrenzte Ansicht. Nur DIREKTE Host-Zuweisung in
dieser Runde (kein Gruppen-Erbe wie bei policies/engine.py -- siehe
[[T-296-ADMIN]] fuer den analogen offenen Punkt bei Host-Gruppen)."""
from astrapi_core.ui.storage import SqliteStorage


def _store():
    return SqliteStorage("user_policies")


def list_user_policies() -> dict:
    return _store().list()


def get_user_policy(policy_id: str) -> dict | None:
    return _store().get(policy_id)


def create_user_policy(policy_id: str, values: dict) -> str:
    return _store().create(policy_id, values)


def update_user_policy(policy_id: str, values: dict) -> None:
    _store().update(policy_id, values)


def delete_user_policy(policy_id: str) -> None:
    _store().delete(policy_id)


def toggle_user_policy(policy_id: str) -> None:
    _store().toggle(policy_id)


def user_policies_for_select() -> list[dict]:
    return [
        {"value": pid, "label": p.get("name") or pid}
        for pid, p in _store().list().items()
    ]


def _entry_sig(entry: dict) -> tuple:
    return (
        entry.get("action"),
        entry.get("shell"),
        bool(entry.get("sudo")),
        tuple(entry.get("ssh_keys") or []),
    )


def resolve_users_for_host(host: dict) -> dict:
    """Vereinigt die entries aller direkt zugewiesenen user_policy_ids
    nach Username. Zwei Policies mit demselben Username, aber
    abweichender Definition -> Konflikt (Username wird ausgeschlossen,
    nicht still aufgeloest -- gleiche Vorsicht wie
    policies/engine.py::resolve_policy_for_host())."""
    ids = list(dict.fromkeys(host.get("user_policy_ids") or []))
    store = _store()

    entries_by_username: dict[str, list[tuple[str, dict]]] = {}
    for pid in ids:
        p = store.get(pid)
        if not p or not p.get("enabled", True):
            continue
        for entry in p.get("entries") or []:
            username = (entry.get("username") or "").strip()
            if not username:
                continue
            entries_by_username.setdefault(username, []).append((pid, entry))

    conflicts = []
    users = []
    for username, entries in entries_by_username.items():
        sigs = {_entry_sig(e) for _, e in entries}
        if len(sigs) > 1:
            conflicts.append({"type": "user", "username": username})
            continue
        users.append(entries[0][1])

    return {"users": users, "conflicts": conflicts}

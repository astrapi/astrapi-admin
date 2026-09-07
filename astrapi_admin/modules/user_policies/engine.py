# astrapi_admin/modules/user_policies/engine.py
"""Nutzer-Policy-Speicherung (SqliteStorage, wie modules/policies/engine.py)
und Aufloesung fuer einen Host.

E-012: eigenes Modul statt Erweiterung der allgemeinen Policies --
Zugriffsverwaltung ist sicherheitskritischer als App-Config und verdient
eine eigene, klar abgegrenzte Ansicht. Ursprünglich nur DIREKTE
Host-Zuweisung (siehe [[T-296-ADMIN]]) -- seit astrapi-hub-Vault E-013
(Nutzerwunsch, claude-deploy-Zugriff über mehrere Dev-Hosts hinweg zu
bündeln) auch über Host-Gruppen zuweisbar, mit demselben
Tier-Vorrangsmuster wie policies/engine.py::resolve_policy_for_host()
(direkte Zuweisung schlägt Gruppen-Zuweisung, Widersprüche auf derselben
Stufe werden nicht still aufgelöst)."""
from astrapi_core.ui.storage import SqliteStorage

_TIER_DIRECT = 2
_TIER_GROUP = 1


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


def group_user_policy_ids(host: dict) -> set[str]:
    """Vereinigung der user_policy_ids aller Gruppen, denen der Host
    angehört -- analog zu policies/engine.py::group_policy_ids()."""
    from astrapi_admin.modules.host_groups.ui.crud import store as groups_store

    result: set[str] = set()
    for gid in host.get("group_ids") or []:
        g = groups_store.get(gid)
        if g:
            result.update(g.get("user_policy_ids") or [])
    return result


def _resolve_by_tier(entries: list[tuple]) -> tuple[tuple, bool]:
    """entries: Liste von (tier, policy_id, signatur, entry). Gewinnt die
    hoechste Vorrangstufe eindeutig, wird sie zurueckgegeben. Tragen
    mehrere Eintraege derselben hoechsten Stufe unterschiedliche
    Signaturen, ist das ein echter Konflikt -- analog zu
    policies/engine.py::_resolve_by_tier()."""
    max_tier = max(e[0] for e in entries)
    top = [e for e in entries if e[0] == max_tier]
    sigs = {e[2] for e in top}
    if len(sigs) > 1:
        return None, True
    return top[0], False


def resolve_users_for_host(host: dict) -> dict:
    """Vereinigt die entries aller zugewiesenen user_policy_ids -- direkt
    UND über Host-Gruppen geerbt (seit E-013) -- nach Username. Direkte
    Zuweisung schlägt Gruppen-Zuweisung; zwei Policies auf derselben
    Vorrangstufe mit abweichender Definition desselben Usernamens ->
    Konflikt (Username wird ausgeschlossen, nicht still aufgelöst --
    gleiche Vorsicht wie policies/engine.py::resolve_policy_for_host())."""
    direct_ids = list(dict.fromkeys(host.get("user_policy_ids") or []))
    direct_set = set(direct_ids)
    group_ids = sorted(group_user_policy_ids(host) - direct_set)

    store = _store()

    def _load(pid: str) -> dict | None:
        p = store.get(pid)
        if not p or not p.get("enabled", True):
            return None
        return p

    direct_policies = [(pid, _load(pid)) for pid in direct_ids]
    direct_policies = [(pid, p) for pid, p in direct_policies if p]
    group_policies = [(pid, _load(pid)) for pid in group_ids]
    group_policies = [(pid, p) for pid, p in group_policies if p]

    entries_by_username: dict[str, list[tuple]] = {}

    def _collect(tier: int, policies: list[tuple[str, dict]]) -> None:
        for pid, pol in policies:
            for entry in pol.get("entries") or []:
                username = (entry.get("username") or "").strip()
                if not username:
                    continue
                entries_by_username.setdefault(username, []).append(
                    (tier, pid, _entry_sig(entry), entry)
                )

    _collect(_TIER_DIRECT, direct_policies)
    _collect(_TIER_GROUP, group_policies)

    conflicts = []
    users = []
    for username, entries in entries_by_username.items():
        winner, conflict = _resolve_by_tier(entries)
        if conflict:
            conflicts.append({"type": "user", "username": username})
            continue
        users.append(winner[3])

    return {"users": users, "conflicts": conflicts}

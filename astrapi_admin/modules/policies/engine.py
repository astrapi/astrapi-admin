# astrapi_admin/modules/policies/engine.py
"""Policy-Speicherung (SqliteStorage, wie scheduler_jobs) und
GPO-artige Aufloesung: host-direkte Zuweisung schlaegt Gruppen-Zuweisung,
Widersprueche auf derselben Vorrangstufe werden NICHT still aufgeloest
(siehe resolve_policy_for_host())."""
from astrapi_core.ui.storage import SqliteStorage

_TIER_DIRECT = 2
_TIER_GROUP = 1


def _store():
    return SqliteStorage("policies")


def list_policies() -> dict:
    return _store().list()


def get_policy(policy_id: str) -> dict | None:
    return _store().get(policy_id)


def create_policy(policy_id: str, values: dict) -> str:
    return _store().create(policy_id, values)


def update_policy(policy_id: str, values: dict) -> None:
    _store().update(policy_id, values)


def delete_policy(policy_id: str) -> None:
    _store().delete(policy_id)


def toggle_policy(policy_id: str) -> None:
    _store().toggle(policy_id)


def policies_for_select() -> list[dict]:
    return [
        {"value": pid, "label": p.get("name") or pid}
        for pid, p in _store().list().items()
    ]


# ── Aufloesung ────────────────────────────────────────────────────────────


def _resolve_by_tier(entries: list[tuple]) -> tuple[object, bool]:
    """entries: Liste von (tier, policy_id, signatur, ...). Gewinnt die
    hoechste Vorrangstufe eindeutig (alle Eintraege dort tragen dieselbe
    Signatur), wird sie zurueckgegeben. Tragen mehrere Eintraege derselben
    hoechsten Stufe unterschiedliche Signaturen, ist das ein echter
    Konflikt -- das Item wird ausgeschlossen statt still aufgeloest."""
    max_tier = max(e[0] for e in entries)
    top = [e for e in entries if e[0] == max_tier]
    sigs = {e[2] for e in top}
    if len(sigs) > 1:
        return None, True
    return top[0], False


def resolve_policy_for_host(host: dict) -> dict:
    """Merged alle fuer den Host geltenden (enabled) Policies -- direkt
    zugewiesene UND ueber Gruppen geerbte -- zu einer OS-aufgeloesten,
    konfliktannotierten Zielvorgabe fuer den Agenten."""
    from astrapi_admin.modules.host_groups.ui.crud import store as groups_store

    direct_ids = list(dict.fromkeys(host.get("policy_ids") or []))
    group_policy_ids = []
    for gid in host.get("group_ids") or []:
        g = groups_store.get(gid)
        if g:
            group_policy_ids.extend(g.get("policy_ids") or [])
    direct_set = set(direct_ids)
    group_only_ids = [pid for pid in dict.fromkeys(group_policy_ids) if pid not in direct_set]

    store = _store()

    def _load(pid: str) -> dict | None:
        p = store.get(pid)
        if not p or not p.get("enabled", True):
            return None
        return p

    direct_policies = [(pid, _load(pid)) for pid in direct_ids]
    direct_policies = [(pid, p) for pid, p in direct_policies if p]
    group_policies = [(pid, _load(pid)) for pid in group_only_ids]
    group_policies = [(pid, p) for pid, p in group_policies if p]

    os_type = host.get("os_type") or ""
    pkg_key = {"archlinux": "packages_arch", "debian": "packages_debian"}.get(os_type)

    packages_required: set[str] = set()
    cfg_entries: dict[str, list] = {}
    svc_entries: dict[str, list] = {}

    def _collect(tier: int, policies: list[tuple[str, dict]]) -> None:
        for pid, pol in policies:
            if pkg_key:
                # "required" ist rein additiv -- zwei Policies koennen sich
                # hier nie widersprechen (anders als vormals present/absent),
                # deshalb ohne Tier-/Konfliktlogik direkt vereinigt.
                packages_required.update(pol.get(pkg_key) or [])
            for cf in pol.get("config_files") or []:
                path = (cf.get("path") or "").strip()
                if not path:
                    continue
                sig = (
                    cf.get("action"),
                    cf.get("content"),
                    cf.get("mode"),
                    cf.get("owner"),
                    cf.get("group"),
                    cf.get("force"),
                )
                cfg_entries.setdefault(path, []).append((tier, pid, sig, cf))
            for svc in pol.get("services") or []:
                name = (svc.get("name") or "").strip()
                if not name:
                    continue
                svc_entries.setdefault(name, []).append((tier, pid, svc.get("state")))

    _collect(_TIER_DIRECT, direct_policies)
    _collect(_TIER_GROUP, group_policies)

    conflicts = []
    config_files = []
    for path, entries in cfg_entries.items():
        winner, conflict = _resolve_by_tier(entries)
        if conflict:
            conflicts.append({"type": "config_file", "path": path})
            continue
        config_files.append(winner[3])

    services = []
    for name, entries in svc_entries.items():
        winner, conflict = _resolve_by_tier(entries)
        if conflict:
            conflicts.append({"type": "service", "name": name})
            continue
        services.append({"name": name, "state": winner[2]})

    return {
        "packages_required": sorted(packages_required),
        "config_files": config_files,
        "services": services,
        "conflicts": conflicts,
        "status": "conflict" if conflicts else "ok",
    }

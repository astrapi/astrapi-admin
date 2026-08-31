# astrapi_admin/modules/hosts/mirror_repos.py
"""Loest host['mirror_repos'] (Slugs auf astrapi-mirror) in fertige
config_files-Eintraege auf -- bewusst NICHT Teil von
policies/engine.py::resolve_policy_for_host(): das bleibt reine
Policy-Merge-Logik, Mirror-Quellen sind ein Host-Attribut (E-005),
keine Policy-Einstellung.

Gruppen-Vererbung (analog zu group_ids/policy_ids, aber rein additiv --
zwei Quellen fuer denselben Slug widersprechen sich nie, anders als
Policy-Inhalte, deshalb keine Tier-/Konfliktlogik noetig)."""
from astrapi_admin.modules.hosts import mirror_client

_SOURCES_DIR = "/etc/apt/sources.list.d"


def group_mirror_repos(host: dict) -> set[str]:
    """Vereinigung der mirror_repos aller Gruppen, denen der Host angehoert."""
    from astrapi_admin.modules.host_groups.ui.crud import store as groups_store

    result: set[str] = set()
    for gid in host.get("group_ids") or []:
        g = groups_store.get(gid)
        if g:
            result.update(g.get("mirror_repos") or [])
    return result


def resolve_mirror_config_files(host: dict, result: dict) -> None:
    """Mutiert result['config_files']/['conflicts']/['status'] in place.

    Zwei Teile:
    1. Fuer jeden aktuell ausgewaehlten Slug eine 'enforce'-Config-Datei.
       Ein nicht erreichbarer/geloeschter Slug blockiert nicht die
       uebrigen (gleiche "ein Fehlschlag stoppt nicht alles"-Philosophie
       wie ueberall im Agenten) -- landet als Eintrag im bestehenden
       conflicts[]/status.
    2. Fuer jeden von astrapi-mirror bekannten, aber NICHT (mehr)
       ausgewaehlten Slug ein 'absent'-Eintrag -- sonst erfaehrt der
       Agent nie, dass ein zuvor gewaehltes Repo wieder abgewaehlt wurde
       (files.remove_if_managed() loescht ohnehin nur, was der Agent
       selbst angelegt hat -- fuer nie ausgewaehlte Slugs also ein
       folgenloser No-op). Best-effort: ist astrapi-mirror kurz nicht
       erreichbar, wird dieser Teil einfach uebersprungen (kein Fehler),
       der naechste Lauf holt es nach."""
    if (host.get("os_type") or "") != "debian":
        return

    selected = set(host.get("mirror_repos") or []) | group_mirror_repos(host)

    for slug in selected:
        content = mirror_client.fetch_sources_content(slug)
        if content is None:
            result["conflicts"].append({"type": "mirror_source", "slug": slug})
            result["status"] = "conflict"
            continue
        result["config_files"].append(
            {
                "path": f"{_SOURCES_DIR}/{slug}.sources",
                "action": "enforce",
                "content": content,
                "mode": "0644",
                "owner": "root",
                "group": "root",
                "force": False,
            }
        )

    for repo in mirror_client.list_debian_repos():
        slug = repo["value"]
        if slug in selected:
            continue
        result["config_files"].append({"path": f"{_SOURCES_DIR}/{slug}.sources", "action": "absent"})

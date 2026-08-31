# astrapi_admin/modules/hosts/mirror_repos.py
"""Loest host['mirror_repos'] (Slugs auf astrapi-mirror) in fertige
config_files-Eintraege auf -- bewusst NICHT Teil von
policies/engine.py::resolve_policy_for_host(): das bleibt reine
Policy-Merge-Logik, Mirror-Quellen sind ein Host-Attribut (E-005),
keine Policy-Einstellung."""
from astrapi_admin.modules.hosts import mirror_client


def resolve_mirror_config_files(host: dict, result: dict) -> None:
    """Mutiert result['config_files']/['conflicts']/['status'] in place.
    Ein nicht erreichbarer/geloeschter Slug blockiert nicht die uebrigen
    (gleiche "ein Fehlschlag stoppt nicht alles"-Philosophie wie ueberall
    im Agenten) -- landet als Eintrag im bestehenden conflicts[]/status,
    kein neues Feld, keine Aenderung an apply.py/summarize() im Agenten
    noetig."""
    if (host.get("os_type") or "") != "debian":
        return
    for slug in host.get("mirror_repos") or []:
        content = mirror_client.fetch_sources_content(slug)
        if content is None:
            result["conflicts"].append({"type": "mirror_source", "slug": slug})
            result["status"] = "conflict"
            continue
        result["config_files"].append(
            {
                "path": f"/etc/apt/sources.list.d/{slug}.sources",
                "action": "enforce",
                "content": content,
                "mode": "0644",
                "owner": "root",
                "group": "root",
                "force": False,
            }
        )

# astrapi_admin/modules/hosts/mirror_client.py
"""HTTP-Client gegen astrapi-mirror -- Grundlage fuer die host-bezogene
Mirror-Quellen-Auswahl (E-005): astrapi-mirror liefert unter `/api/debian`
bereits die vollstaendige Repo-Liste und unter
`/files/debian/{slug}/{slug}.sources` eine fertig gerenderte DEB822-Datei
je Repo -- kein neuer Code in astrapi-mirror noetig, nur ein duenner
Client hier. Beide Aufrufe liefern bewusst einen "leeren"/None-Fallwert
statt eine Exception zu werfen -- ein kurz nicht erreichbarer Mirror darf
weder den Host-Dialog noch den Agent-Policy-Abruf zum Absturz bringen.

WICHTIG (echt gegen den Produktivmirror verifiziert): httpx prueft
Zertifikate per Default gegen das von certifi mitgelieferte Bundle, NICHT
gegen den System-Truststore -- `mirror.simpsons.lan`s Zertifikat (interne
CA, vom System via `update-ca-certificates`/`update-ca-trust` vertraut)
wurde deshalb als ungueltig abgelehnt, obwohl `curl` denselben Aufruf
anstandslos akzeptiert. Fix: `verify=ssl.create_default_context()` laedt
explizit den System-Truststore. Zusaetzlich `follow_redirects=True` --
`/api/debian` antwortet mit 307 (Normalisierung), von `curl -L` bisher
unbemerkt mitgemacht."""
import ssl

import httpx

_TIMEOUT = 5.0
_SSL_CONTEXT = ssl.create_default_context()


def _base_url() -> str:
    from astrapi_core.ui.settings_registry import get_module

    return (get_module("hosts", "mirror_base_url", "") or "").rstrip("/")


def list_debian_repos() -> list[dict]:
    """[{"value": slug, "label": label}, ...] der aktivierten Debian-Repos."""
    base = _base_url()
    if not base:
        return []
    try:
        r = httpx.get(f"{base}/api/debian", timeout=_TIMEOUT, verify=_SSL_CONTEXT, follow_redirects=True)
        r.raise_for_status()
        repos = r.json().get("debian", {})
    except (httpx.HTTPError, ValueError):
        return []
    return [
        {"value": repo["slug"], "label": repo.get("label") or repo["slug"]}
        for repo in repos.values()
        if repo.get("enabled") and repo.get("slug")
    ]


def fetch_sources_content(slug: str) -> str | None:
    """Fertig gerenderte .sources-Datei fuer einen Repo-Slug, None bei Fehler."""
    base = _base_url()
    if not base:
        return None
    try:
        r = httpx.get(
            f"{base}/files/debian/{slug}/{slug}.sources",
            timeout=_TIMEOUT,
            verify=_SSL_CONTEXT,
            follow_redirects=True,
        )
        r.raise_for_status()
        return r.text
    except httpx.HTTPError:
        return None

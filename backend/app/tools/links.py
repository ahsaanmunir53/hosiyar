"""Link checks: shorteners, look-alike domains, domain age (RDAP) and Google Safe Browsing.

Safety: the checker never opens the suspicious website itself. For short links it only asks
the shortening service where the link points (the Location header) and stops there.
"""

import asyncio
import logging
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx

from app.config import Settings
from app.core.urls import split_url
from app.rules.brands import RISKY_TLDS, URL_SHORTENERS, lookalike_brand, official_brand_for
from app.rules.catalog import official_brand_dict

log = logging.getLogger(__name__)

_RDAP_CACHE: dict[str, tuple[dict, float]] = {}
_RDAP_TTL = 6 * 3600


def _homograph_brand(p: dict):
    """A host written with look-alike letters ("һbl.com") imitates the brand its folded form belongs to."""
    folded = p.get("homograph_of")
    if not folded:
        return None
    f = split_url(folded)
    return official_brand_for(f["registered_domain"], f["host"]) or lookalike_brand(f["host"], f["registered_domain"], f["domain"])


def _static_report(url: str, settings: Settings) -> dict:
    p = split_url(url)
    look = _homograph_brand(p) or lookalike_brand(p["host"], p["registered_domain"], p["domain"])
    return {
        "url": p["url"],
        "host": p["host"],
        "registered_domain": p["registered_domain"],
        "suffix": p["suffix"],
        "is_ip": p["is_ip"],
        "is_punycode": p["is_punycode"],
        "not_https": p["scheme"] != "https",
        "is_shortener": p["registered_domain"] in URL_SHORTENERS,
        "risky_tld": p["suffix"].split(".")[-1] in RISKY_TLDS if p["suffix"] else False,
        "official_brand": None if p.get("homograph_of") else official_brand_dict(p["registered_domain"], p["host"]),
        "homograph_of": p.get("homograph_of"),
        "lookalike_brand": {"key": look.key, "name": look.name, "kind": look.kind} if look else None,
        "expanded_url": None,
        "final_registered_domain": p["registered_domain"],
        "domain_age_days": None,
        "safe_browsing_threats": [],
        "new_domain_days": settings.new_domain_days,
        "checks": ["structure"],
        "errors": [],
    }


def _apply_final(report: dict, final_url: str, settings: Settings) -> None:
    """Re-run the structural checks on the destination of a short link."""
    final = _static_report(final_url, settings)
    report["expanded_url"] = final["url"]
    report["final_registered_domain"] = final["registered_domain"]
    report["official_brand"] = final["official_brand"]
    report["lookalike_brand"] = final["lookalike_brand"] or report["lookalike_brand"]
    report["is_ip"] = final["is_ip"] or report["is_ip"]
    report["is_punycode"] = final["is_punycode"] or report["is_punycode"]
    report["risky_tld"] = report["risky_tld"] or final["risky_tld"]
    report["suffix"] = final["suffix"] or report["suffix"]


async def _expand_short_link(client: httpx.AsyncClient, url: str, max_hops: int = 4) -> str | None:
    current = url
    for _ in range(max_hops):
        resp = await client.head(current, follow_redirects=False)
        if resp.status_code in (405, 400):
            resp = await client.get(current, follow_redirects=False)
        location = resp.headers.get("location")
        if not location:
            return current if current != url else None
        current = urljoin(current, location)
        if split_url(current)["registered_domain"] not in URL_SHORTENERS:
            return current
    return current


def _vcard(entity: dict, field: str) -> str | None:
    for item in (entity.get("vcardArray") or [None, []])[1]:
        if isinstance(item, list) and len(item) >= 4 and item[0] == field and isinstance(item[3], str):
            return item[3]
    return None


def _parse_rdap(data: dict) -> dict:
    info: dict = {"age_days": None, "registered": None, "registrar": None, "abuse_email": None}
    for event in data.get("events", []):
        if event.get("eventAction") == "registration" and event.get("eventDate"):
            registered = datetime.fromisoformat(event["eventDate"].replace("Z", "+00:00"))
            info["registered"] = registered.date().isoformat()
            info["age_days"] = max(0, (datetime.now(UTC) - registered).days)
            break
    for entity in data.get("entities", []):
        if "registrar" in (entity.get("roles") or []):
            info["registrar"] = _vcard(entity, "fn")
            for sub in entity.get("entities", []):
                if "abuse" in (sub.get("roles") or []):
                    info["abuse_email"] = _vcard(sub, "email")
        if not info["abuse_email"] and "abuse" in (entity.get("roles") or []):
            info["abuse_email"] = _vcard(entity, "email")
    return info


async def rdap_info(client: httpx.AsyncClient, registered_domain: str) -> dict:
    """Registration date, registrar and abuse contact from RDAP (cached for six hours)."""
    now = datetime.now(UTC).timestamp()
    cached = _RDAP_CACHE.get(registered_domain)
    if cached and now - cached[1] < _RDAP_TTL:
        return cached[0]
    resp = await client.get(
        f"https://rdap.org/domain/{registered_domain}",
        follow_redirects=True,
        headers={"Accept": "application/rdap+json"},
    )
    info = _parse_rdap(resp.json()) if resp.status_code == 200 else {
        "age_days": None, "registered": None, "registrar": None, "abuse_email": None}
    info["rdap_url"] = f"https://rdap.org/domain/{registered_domain}"
    _RDAP_CACHE[registered_domain] = (info, now)
    return info


async def domain_age_days(client: httpx.AsyncClient, registered_domain: str) -> int | None:
    return (await rdap_info(client, registered_domain))["age_days"]


async def safe_browsing_threats(client: httpx.AsyncClient, api_key: str, urls: list[str]) -> dict[str, list[str]]:
    """Look URLs up with the Safe Browsing v5 urls:search method."""
    # The key goes in a header so it never appears in a logged URL.
    resp = await client.get(
        "https://safebrowsing.googleapis.com/v5/urls:search",
        params=[("urls", u) for u in urls[:50]],
        headers={"X-Goog-Api-Key": api_key},
    )
    resp.raise_for_status()
    found: dict[str, list[str]] = {}
    for item in resp.json().get("threats", []):
        found[item.get("url", "")] = list(item.get("threatTypes", []))
    return found


async def check_links(urls: list[str], settings: Settings, client: httpx.AsyncClient | None) -> list[dict]:
    reports = [_static_report(u, settings) for u in urls]
    if not reports or not settings.enable_network_checks or client is None:
        return reports

    async def enrich(report: dict) -> None:
        if report["is_shortener"]:
            try:
                final = await _expand_short_link(client, report["url"])
                if final:
                    _apply_final(report, final, settings)
                report["checks"].append("expand")
            except httpx.HTTPError as exc:
                report["errors"].append(f"expand: {type(exc).__name__}")
        dom = report["final_registered_domain"]
        if dom and not report["official_brand"] and not report["is_ip"]:
            try:
                report["domain_age_days"] = await domain_age_days(client, dom)
                report["checks"].append("rdap")
            except (httpx.HTTPError, ValueError) as exc:
                report["errors"].append(f"rdap: {type(exc).__name__}")

    await asyncio.gather(*(enrich(r) for r in reports))

    if settings.safe_browsing_api_key:
        lookups = {r["url"]: r for r in reports}
        lookups.update({r["expanded_url"]: r for r in reports if r["expanded_url"]})
        try:
            threats = await safe_browsing_threats(client, settings.safe_browsing_api_key, list(lookups))
            for url, kinds in threats.items():
                if url in lookups:
                    lookups[url]["safe_browsing_threats"] = kinds
            for r in reports:
                r["checks"].append("safe_browsing")
        except (httpx.HTTPError, ValueError) as exc:
            # Only the error type and status: the message would include the looked-up links.
            status = getattr(getattr(exc, "response", None), "status_code", "")
            log.warning("Safe Browsing lookup failed: %s %s", type(exc).__name__, status)
            for r in reports:
                r["errors"].append(f"safe_browsing: {type(exc).__name__}")
    return reports

import httpx
import pytest
import respx

from app.core.urls import extract_urls, split_url
from app.rules.brands import lookalike_brand
from app.tools import links as link_tools


@pytest.mark.parametrize(
    ("url", "brand"),
    [
        ("hbl-verify.com", "hbl"),
        ("https://hbl.com.secure-login.xyz/a", "hbl"),
        ("jazzcash-reward.xyz", "jazzcash"),
        ("easypaissa.com", "easypaisa"),
        ("g00gle-security-check.com", "google"),
        ("bisp.gov.pk.apply-now.top", "bisp"),
        ("hbl.com", None),
        ("jazzcash.com.pk", None),
        ("jazzfestival.com", None),
        ("googleusercontent.com", None),
        ("dawn.com", None),
    ],
)
def test_lookalike(url, brand):
    p = split_url(url)
    found = lookalike_brand(p["host"], p["registered_domain"], p["domain"])
    assert (found.key if found else None) == brand


def test_extract_urls_skips_file_names():
    urls = extract_urls("See bit.ly/abc and photo.jpg and https://hbl.com/x, call 0300")
    assert urls == ["http://bit.ly/abc", "https://hbl.com/x"]


async def test_static_report_without_network(settings):
    reports = await link_tools.check_links(["http://jazzcash-reward.xyz/claim"], settings, None)
    r = reports[0]
    assert r["lookalike_brand"]["key"] == "jazzcash"
    assert r["risky_tld"] is True
    assert r["checks"] == ["structure"]


@respx.mock
async def test_short_link_is_expanded_without_visiting_destination(settings):
    settings = settings.model_copy(update={"enable_network_checks": True})
    link_tools._RDAP_CACHE.clear()
    respx.head("http://bit.ly/x1").mock(
        return_value=httpx.Response(301, headers={"location": "https://hbl-secure.top/login"})
    )
    dest = respx.get("https://hbl-secure.top/login")
    respx.get("https://rdap.org/domain/hbl-secure.top").mock(
        return_value=httpx.Response(200, json={"events": [{"eventAction": "registration", "eventDate": "2026-10-10T00:00:00Z"}]})
    )
    async with httpx.AsyncClient() as client:
        r = (await link_tools.check_links(["http://bit.ly/x1"], settings, client))[0]
    assert r["expanded_url"] == "https://hbl-secure.top/login"
    assert r["lookalike_brand"]["key"] == "hbl"
    assert r["domain_age_days"] is not None and r["domain_age_days"] < 90
    assert not dest.called


@respx.mock
async def test_safe_browsing_hit(settings):
    settings = settings.model_copy(update={"enable_network_checks": True, "safe_browsing_api_key": "k"})
    link_tools._RDAP_CACHE.clear()
    respx.get("https://rdap.org/domain/evil-site.com").mock(return_value=httpx.Response(404))
    sb = respx.get("https://safebrowsing.googleapis.com/v5/urls:search").mock(
        return_value=httpx.Response(200, json={"threats": [{"url": "http://evil-site.com/x", "threatTypes": ["SOCIAL_ENGINEERING"]}]})
    )
    async with httpx.AsyncClient() as client:
        r = (await link_tools.check_links(["http://evil-site.com/x"], settings, client))[0]
    assert r["safe_browsing_threats"] == ["SOCIAL_ENGINEERING"]
    sent = sb.calls[0].request
    assert "key=" not in str(sent.url) and sent.headers["x-goog-api-key"] == "k"
    assert "safe_browsing" in r["checks"]


@respx.mock
async def test_network_errors_are_recorded_not_raised(settings):
    settings = settings.model_copy(update={"enable_network_checks": True})
    link_tools._RDAP_CACHE.clear()
    respx.get("https://rdap.org/domain/slow-site.com").mock(side_effect=httpx.ConnectTimeout("t"))
    async with httpx.AsyncClient() as client:
        r = (await link_tools.check_links(["http://slow-site.com"], settings, client))[0]
    assert r["domain_age_days"] is None
    assert any(e.startswith("rdap") for e in r["errors"])


def test_government_sites_are_official():
    from app.rules.catalog import official_brand_dict

    assert official_brand_dict("psca.gop.pk", "echallan.psca.gop.pk")["key"] == "psca"
    assert official_brand_dict("punjab.gov.pk", "epay.punjab.gov.pk")["key"] == "epay_punjab"
    assert official_brand_dict("punjab.gov.pk", "lahore.punjab.gov.pk")["kind"] == "government"
    for host in ("repayment.com", "bankofpunjab.com", "punjabi.com"):
        p = split_url(host)
        assert lookalike_brand(p["host"], p["registered_domain"], p["domain"]) is None


def test_gemini_style_content_parts_become_plain_text():
    from app.ai.llm import text_of

    parts = [{"type": "text", "text": "This message has warning signs.", "extras": {"signature": "abc"}}]
    assert text_of(type("M", (), {"content": parts})()) == "This message has warning signs."
    assert text_of(type("M", (), {"content": "plain"})()) == "plain"

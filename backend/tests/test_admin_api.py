"""HTTP tests for the review panel, file uploads, lookups, cron jobs, captcha and privacy."""

import io

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.auth import hash_password, make_token, read_token, verify_password
from app.main import create_app
from tests.helpers import PHISHING_EMAIL, make_pdf

ADMIN = {"email": "admin@example.org", "password": "correct horse battery"}


@pytest.fixture
def admin_client(settings):
    s = settings.model_copy(update={"admin_email": ADMIN["email"], "admin_password": ADMIN["password"], "cron_secret": "cron-s3cret"})
    with TestClient(create_app(s)) as c:
        yield c


def login(c, email=ADMIN["email"], password=ADMIN["password"]) -> dict:
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_password_hash_and_token(settings):
    h = hash_password("a long password")
    assert verify_password("a long password", h) and not verify_password("wrong", h)
    token = make_token(settings, "a@b.org", "admin")
    assert read_token(settings, token)["sub"] == "a@b.org"
    assert read_token(settings, token[:-2] + "xx") is None
    assert read_token(settings.model_copy(update={"auth_secret": "other"}), token) is None


def test_login_and_roles(admin_client):
    c = admin_client
    assert c.post("/api/auth/login", json={"email": ADMIN["email"], "password": "nope"}).status_code == 401
    assert c.get("/api/admin/reports").status_code == 401
    h = login(c)
    assert c.get("/api/auth/me", headers=h).json()["role"] == "admin"
    r = c.post("/api/admin/users", headers=h, json={"email": "analyst@example.org", "password": "another long pass", "role": "analyst"})
    assert r.status_code == 200
    ah = login(c, "analyst@example.org", "another long pass")
    assert c.get("/api/admin/reports", headers=ah).status_code == 200
    assert c.get("/api/admin/users", headers=ah).status_code == 403  # admin only
    uid = r.json()["id"]
    c.post(f"/api/admin/users/{uid}/deactivate", headers=h)
    assert c.get("/api/admin/reports", headers=ah).status_code == 401


def test_review_queue_approve_and_watchlist(admin_client):
    c = admin_client
    h = login(c)
    body = c.post("/api/analyze", json={"text": "Aap ka inaam nikla hai, details ke liye 03451234567 par rabta karein", "share": True}).json()
    assert body["report_status"] == "pending"
    queue = c.get("/api/admin/reports?status=pending", headers=h).json()
    assert queue["reports"][0]["id"] == body["id"]
    assert "03451234567" not in str(queue)  # only redacted text and fingerprints
    assert c.post(f"/api/admin/reports/{body['id']}/approve", headers=h, json={"note": "prize scam"}).status_code == 200
    look = c.post("/api/lookup", json={"value": "0345-1234567"}).json()
    assert look["status"] == "reported"

    w = c.post("/api/admin/watchlist", headers=h, json={"kind": "domain", "value": "https://bisp-claim.top/x", "note": "fake BISP"})
    assert w.status_code == 200 and w.json()["label"] == "bisp-claim.top"
    assert c.post("/api/admin/watchlist", headers=h, json={"kind": "domain", "value": "bisp-claim.top"}).status_code == 409
    result = c.post("/api/analyze", json={"text": "Check your status at bisp-claim.top"}).json()
    assert result["verdict"] == "likely_scam"
    assert any(r["id"] == "watchlist_match" for r in result["reasons"])
    stix = c.get("/api/admin/export/stix", headers=h).json()
    assert stix["type"] == "bundle"
    overview = c.get("/api/admin/overview", headers=h).json()
    assert overview["watchlist"] == 1


def test_admin_official_domain_changes_link_checks(admin_client):
    c = admin_client
    h = login(c)
    before = c.post("/api/analyze", json={"text": "Your Meezan statement is ready at meezan-statements.com"}).json()
    assert before["links"][0]["official_brand"] is None
    r = c.post("/api/admin/official-domains", headers=h, json={"domain": "meezan-statements.com", "name": "Meezan statements", "kind": "bank"})
    assert r.status_code == 200
    after = c.post("/api/analyze", json={"text": "Your Meezan statement is ready at meezan-statements.com"}).json()
    assert after["links"][0]["official_brand"]["name"] == "Meezan statements"


def test_cron_needs_secret(admin_client):
    c = admin_client
    assert c.post("/api/cron/weekly").status_code == 401
    assert c.post("/api/cron/weekly", headers={"X-Cron-Secret": "wrong"}).status_code == 401
    r = c.post("/api/cron/weekly", headers={"X-Cron-Secret": "cron-s3cret"})
    assert r.status_code == 200 and r.json()["delivered"] is False
    assert c.get("/api/alerts/latest").json()["alert"]["checks"] == 0
    assert c.post("/api/cron/purge", headers={"X-Cron-Secret": "cron-s3cret"}).status_code == 200


def test_cron_is_off_without_secret(client):
    assert client.post("/api/cron/weekly", headers={"X-Cron-Secret": "x"}).status_code == 404


def test_pdf_and_email_uploads(client):
    pdf = make_pdf("Pay your unpaid challan at psca-echallan.cc today", link="http://psca-echallan.cc/pay", javascript=True)
    r = client.post("/api/analyze/upload", files={"file": ("challan.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_kind"] == "pdf"
    assert body["file_info"]["active_content"] == ["JavaScript"]
    assert any(x["id"] == "pdf_active_content" for x in body["reasons"])

    r = client.post("/api/analyze/upload", files={"file": ("mail.eml", io.BytesIO(PHISHING_EMAIL.encode()), "message/rfc822")})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "likely_scam"
    assert body["file_info"]["auth"]["dmarc"] == "fail"
    ids = {x["id"] for x in body["reasons"]}
    assert {"email_brand_mismatch", "email_auth_failed", "risky_attachment"} <= ids
    assert next(x for x in body["reasons"] if x["id"] == "email_brand_mismatch")["hard"] is True

    pasted = client.post("/api/analyze/email", json={"raw": PHISHING_EMAIL})
    assert pasted.status_code == 200 and pasted.json()["source_kind"] == "email"
    bad = client.post("/api/analyze/email", json={"raw": "Dear customer, your account is blocked, call now."})
    assert bad.status_code == 422


def test_qr_payment_code(client):
    def tlv(t, v):
        return f"{t}{len(v):02d}{v}"

    from app.files.qr import crc16_ccitt

    body = tlv("00", "01") + tlv("01", "11") + tlv("26", tlv("00", "PK.RAAST")) + tlv("53", "586") + tlv("59", "QUICK CASH") + "6304"
    r = client.post("/api/analyze", json={"text": body + crc16_ccitt(body), "source_kind": "qr"}).json()
    assert r["source_kind"] == "qr"
    assert r["file_info"]["payment"]["merchant_name"] == "QUICK CASH"
    assert r["verdict"] == "no_red_flags"  # a payment code on its own is not a scam

    refund = tlv("00", "01") + tlv("26", tlv("00", "PK.RAAST")) + tlv("59", "BISP REFUND DESK") + "6304"
    r = client.post("/api/analyze", json={"text": refund + crc16_ccitt(refund), "source_kind": "qr"}).json()
    assert any(x["id"] == "receive_by_scan" for x in r["reasons"])
    assert r["verdict"] != "no_red_flags"


@respx.mock
def test_turnstile_captcha(settings):
    s = settings.model_copy(update={"turnstile_secret": "ts-secret", "integration_key": "ext-key"})
    verify = respx.post("https://challenges.cloudflare.com/turnstile/v0/siteverify").mock(
        side_effect=lambda req: httpx.Response(200, json={"success": b"good-token" in req.content}))
    with TestClient(create_app(s)) as c:
        assert c.post("/api/analyze", json={"text": "hello"}).status_code == 403
        assert c.post("/api/analyze", json={"text": "hello", "captcha_token": "bad-token"}).status_code == 403
        assert c.post("/api/analyze", json={"text": "hello", "captcha_token": "good-token"}).status_code == 200
        assert c.post("/api/analyze", json={"text": "hello"}, headers={"X-Hoshiyar-Key": "ext-key"}).status_code == 200
        assert c.get("/api/health").json()["captcha"] is True
    assert verify.call_count == 2


def test_family_code_needs_telegram(client):
    assert client.post("/api/family/code", json={"client_id": "browser-123456"}).status_code == 503
    assert client.post("/api/family/status", json={"client_id": "browser-123456"}).json()["available"] is False


def test_privacy_quality_and_forget(client):
    client.post("/api/analyze", json={"text": "hello there", "client_id": "browser-forget-1"})
    p = client.get("/api/privacy").json()
    assert p["retention_days"]["checks"] == 180
    q = client.get("/api/quality").json()
    assert q["eval"]["test"]["messages"] == 60
    assert q["redteam"]["runs"][0]["total"] >= 20
    gone = client.post("/api/me/forget", json={"client_id": "browser-forget-1"}).json()
    assert gone["deleted"]["analyses"] == 1


def test_public_campaigns_hide_fingerprints(client):
    for i, text in enumerate([
        "HBL: account blocked. Verify at hbl-verify.top/login and share the OTP. Call 03001234567",
        "HBL customer: confirm at hbl-verify.top/secure with your OTP. Helpline 03001234567",
    ]):
        client.post("/api/analyze", json={"text": text, "share": True, "client_id": f"browser-c{i}"})
    campaigns = client.get("/api/campaigns").json()["campaigns"]
    assert campaigns and campaigns[0]["report_count"] == 2
    assert {i["kind"] for i in campaigns[0]["indicators"]} == {"domain"}


def test_receipt_without_key_still_gives_advice(client):
    r = client.post("/api/receipt", files={"file": ("pay.png", io.BytesIO(b"\x89PNG fake"), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["experimental"] is True and body["unavailable"] and len(body["advice"]) == 3


def test_login_disabled_in_production_with_default_secret(settings):
    s = settings.model_copy(update={"app_env": "production", "admin_email": ADMIN["email"], "admin_password": ADMIN["password"]})
    with TestClient(create_app(s)) as c:
        assert c.post("/api/auth/login", json=ADMIN).status_code == 503


def test_forged_token_with_default_secret_is_refused_in_production(settings):
    from app.auth import DEFAULT_SECRET

    s = settings.model_copy(update={"app_env": "production", "admin_email": ADMIN["email"], "admin_password": ADMIN["password"]})
    forged = make_token(s.model_copy(update={"auth_secret": DEFAULT_SECRET}), ADMIN["email"], "admin")
    with TestClient(create_app(s)) as c:
        assert c.get("/api/admin/users", headers={"Authorization": f"Bearer {forged}"}).status_code == 503


def test_odd_tokens_do_not_crash(admin_client):
    for token in (b"\xc3\xbcn\xc3\xafcode.sig", b"no-dot", b"a.b.c"):
        assert admin_client.get("/api/auth/me", headers={"Authorization": b"Bearer " + token}).status_code == 401


def test_web_client_cannot_claim_a_telegram_identity(client):
    assert client.post("/api/analyze", json={"text": "hello there", "client_id": "tg:12345678"}).status_code == 422
    assert client.post("/api/family/status", json={"client_id": "tg:12345678"}).status_code == 422


def test_rate_limit_ignores_spoofed_forwarded_for(settings):
    """Render chain: [client-sent..., visitor, Cloudflare edge, Render hop]."""
    s = settings.model_copy(update={"rate_limit_per_minute": 3, "trusted_proxy_hops": 3, "client_ip_header": ""})
    with TestClient(create_app(s)) as c:
        codes = [c.post("/api/lookup", json={"value": "03001234567"},
                        headers={"X-Forwarded-For": f"6.6.6.{i}, 203.0.113.9, 172.68.1.1, 10.0.0.5"}).status_code
                 for i in range(5)]
        assert codes == [200, 200, 200, 429, 429]
        # Different visitors behind the same Cloudflare edge and Render hop keep separate limits.
        other = c.post("/api/lookup", json={"value": "03001234567"},
                       headers={"X-Forwarded-For": "198.51.100.7, 172.68.1.1, 10.0.0.5"})
        assert other.status_code == 200


def test_rate_limit_uses_cloudflare_visitor_header(settings):
    s = settings.model_copy(update={"rate_limit_per_minute": 2})
    with TestClient(create_app(s)) as c:
        codes = [c.post("/api/lookup", json={"value": "03001234567"},
                        headers={"CF-Connecting-IP": "203.0.113.9", "X-Forwarded-For": f"6.6.6.{i}"}).status_code
                 for i in range(3)]
    assert codes == [200, 200, 429]


def test_takedown_rejects_malformed_url(client):
    assert client.post("/api/takedown", json={"url": "http://[::1"}).status_code == 422


def test_email_subject_is_redacted_in_the_result(client):
    raw = PHISHING_EMAIL.replace("Subject: Your HBL account will be suspended",
                                 "Subject: Account 0300-1234567 suspended, contact my.name@gmail.com")
    body = client.post("/api/analyze/email", json={"raw": raw}).json()
    assert "1234567" not in body["file_info"]["subject"] and "my.name" not in body["file_info"]["subject"]
    assert all("?" not in link for link in body["file_info"]["links"])


def test_partner_stix_feed_needs_the_integration_key(settings, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as c:
        assert c.get("/api/stix").status_code == 404  # not set up
    keyed = settings.model_copy(update={"integration_key": "partner-key-for-tests", "sqlite_path": str(tmp_path / "k.db")})
    with TestClient(create_app(keyed)) as c:
        assert c.get("/api/stix").status_code == 401
        assert c.get("/api/stix", headers={"X-Integration-Key": "wrong"}).status_code == 401
        bundle = c.get("/api/stix", headers={"X-Integration-Key": "partner-key-for-tests"}).json()
        assert bundle["type"] == "bundle" and bundle["objects"][0]["type"] == "identity"

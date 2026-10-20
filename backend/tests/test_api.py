import io

import httpx
import respx

from app.config import Settings
from app.main import create_app


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["storage"] == "local"
    assert body["llm"] is False


def test_health_ai_without_keys(client):
    body = client.get("/api/health/ai").json()
    assert body["ok"] is False
    assert body["models"] == []


def test_analyze_and_followup(client):
    r = client.post("/api/analyze", json={
        "text": "Mubarak ho! Aap ki BISP 25000 ki raqam aa gayi. 500 fee is number par bhejein 03001234567",
        "sender": "03001234567",
        "client_id": "browser-1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "likely_scam"
    assert body["category"]["id"] == "government_benefit"
    assert "03001234567" not in body["analyzed_text"]
    assert body["redactions"]["PHONE"] == 1
    assert {"en", "ur", "roman"} == set(body["reasons"][0]["title"])
    assert any(s["id"] == "bisp_official" for s in body["next_steps"])

    f = client.post("/api/followup", json={"thread_id": body["thread_id"], "question": "how do I report this?"})
    assert f.status_code == 200
    assert "nccia" in f.json()["answer"]["answer"].lower()


def test_followup_for_unknown_thread_is_404(client):
    r = client.post("/api/followup", json={"thread_id": "does-not-exist", "question": "what now?"})
    assert r.status_code == 404


def test_validation(client):
    assert client.post("/api/analyze", json={"text": ""}).status_code == 422
    assert client.post("/api/analyze", json={"text": "x" * 5000}).status_code == 422


def test_upload_needs_keys(client):
    files = {"file": ("shot.png", io.BytesIO(b"\x89PNG fake"), "image/png")}
    r = client.post("/api/analyze/upload", files=files)
    assert r.status_code == 503
    assert "GOOGLE_API_KEY" in r.json()["detail"]
    r = client.post("/api/analyze/upload", files={"file": ("a.txt", io.BytesIO(b"hi"), "text/plain")})
    assert r.status_code == 415


def test_stats_and_rules(client):
    client.post("/api/analyze", json={"text": "HBL: share the OTP you received with our agent to keep your account", "share": True})
    stats = client.get("/api/stats").json()
    assert stats["total_checks"] == 1
    assert stats["verdicts"]["likely_scam"] == 1
    assert stats["includes_sample_data"] is False
    assert len(stats["daily"]) == 14
    rules = client.get("/api/rules").json()
    assert rules["version"] and len(rules["rules"]) > 20


def test_sample_data_is_labelled(settings):
    app = create_app(settings.model_copy(update={"seed_demo_data": True}))
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        stats = c.get("/api/stats").json()
    assert stats["includes_sample_data"] is True
    assert stats["sample_rows"] > 0


def test_rate_limit(settings):
    from fastapi.testclient import TestClient

    app = create_app(settings.model_copy(update={"rate_limit_per_minute": 2}))
    with TestClient(app) as c:
        codes = [c.post("/api/analyze", json={"text": "hello there"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


@respx.mock
def test_telegram_webhook(settings: Settings):
    from fastapi.testclient import TestClient

    s = settings.model_copy(update={"telegram_bot_token": "TOKEN", "telegram_webhook_secret": "sec"})
    sent = respx.post("https://api.telegram.org/botTOKEN/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
    respx.post("https://api.telegram.org/botTOKEN/sendChatAction").mock(return_value=httpx.Response(200, json={"ok": True}))
    app = create_app(s)
    with TestClient(app) as c:
        assert c.post("/api/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "bad"}).status_code == 401
        update = {"message": {"chat": {"id": 42}, "text": "Maine galti se aap ko code bhej diya, please wapas bhej dein"}}
        r = c.post("/api/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "sec"})
        assert r.status_code == 200
    assert sent.called
    payload = sent.calls[-1].request.content.decode()
    assert "42" in payload and ("Ghaliban fraud" in payload or "Likely scam" in payload)

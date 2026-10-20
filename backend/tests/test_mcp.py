"""The MCP server exposes Hoshiyar as tools and passes the rule book's verdict through unchanged."""

import json

import httpx
import respx
from mcp import Client

from app.mcp_server import create_server

ANALYSIS = {
    "verdict": "likely_scam", "score": 90, "language": "en",
    "category": {"id": "bank_wallet", "label": {"en": "Bank or wallet impersonation", "ur": "", "roman": ""}},
    "explanation": {"text": "This looks like a scam."},
    "reasons": [{"title": {"en": "Asks for your OTP"}, "why": {"en": "Banks never ask."}, "hard": True, "weight": 45}],
    "links": [{"url": "http://hbl-verify.top", "official_brand": None, "lookalike_brand": {"name": "HBL"}, "domain_age_days": 3}],
    "next_steps": [{"text": {"en": "Do not reply."}}], "similar": [], "rules_version": "x",
}


@respx.mock
async def test_mcp_tools_call_the_api():
    respx.post("http://hoshiyar.test/api/analyze").mock(return_value=httpx.Response(200, json=ANALYSIS))
    respx.post("http://hoshiyar.test/api/lookup").mock(return_value=httpx.Response(422, json={"detail": "Enter a phone number"}))
    async with httpx.AsyncClient(base_url="http://hoshiyar.test") as http:
        server = create_server(http)
        async with Client(server) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            assert names == {"check_message", "lookup", "recent_campaigns", "reporting_channels"}
            result = await client.call_tool("check_message", {"text": "HBL: share your OTP at hbl-verify.top"})
            data = json.loads(result.content[0].text)
            assert data["verdict"] == "likely_scam"
            assert data["links"][0]["imitates"] == "HBL"
            assert data["reasons"][0]["decisive"] is True
            err = json.loads((await client.call_tool("lookup", {"value": "??"})).content[0].text)
            assert err["error"].startswith("HTTP 422")

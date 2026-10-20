"""MCP server: lets an AI assistant (Claude Desktop, Cursor, any MCP client) use Hoshiyar as a tool.

It runs on your computer over stdio and calls your Hoshiyar API, so no keys are shared
with the assistant. It needs only `mcp` and `httpx` (both in requirements.txt):

    HOSHIYAR_API_URL=https://your-api.onrender.com python app/mcp_server.py

Claude Desktop config (claude_desktop_config.json), with the full paths on your computer:

    {"mcpServers": {"hoshiyar": {
        "command": "C:\\path\\to\\backend\\.venv\\Scripts\\python.exe",
        "args": ["C:\\path\\to\\backend\\app\\mcp_server.py"],
        "env": {"HOSHIYAR_API_URL": "https://your-api.onrender.com"}}}}
"""

import os
from typing import Literal

import httpx
from mcp.server.mcpserver import MCPServer

INSTRUCTIONS = (
    "Hoshiyar checks messages people in Pakistan receive (SMS, WhatsApp, email) for scam signs, in English, "
    "Urdu and Roman Urdu. A fixed rule book decides the verdict; report it as given and do not override it. "
    "Never ask the user for OTPs, PINs or passwords."
)


def _short(result: dict) -> dict:
    """The parts of an analysis an assistant needs, without the full trace."""
    lang = result.get("language", "en")
    return {
        "verdict": result["verdict"],
        "score": result["score"],
        "category": result["category"]["label"]["en"],
        "explanation": result["explanation"]["text"],
        "reasons": [{"title": r["title"]["en"], "why": r["why"]["en"], "decisive": r["hard"]} for r in result["reasons"] if r["weight"] > 0],
        "links": [{"url": lk["url"], "official": (lk.get("official_brand") or {}).get("name"),
                   "imitates": (lk.get("lookalike_brand") or {}).get("name"), "age_days": lk.get("domain_age_days")}
                  for lk in result.get("links", [])],
        "next_steps": [s["text"][lang] for s in result.get("next_steps", [])],
        "similar_known_scams": len(result.get("similar", [])),
        "rules_version": result.get("rules_version"),
    }


def create_server(client: httpx.AsyncClient | None = None) -> MCPServer:
    base = os.environ.get("HOSHIYAR_API_URL", "http://localhost:8000").rstrip("/")
    headers = {"X-Hoshiyar-Key": os.environ["HOSHIYAR_KEY"]} if os.environ.get("HOSHIYAR_KEY") else {}
    http = client or httpx.AsyncClient(base_url=base, timeout=90, headers=headers)
    server = MCPServer("Hoshiyar", instructions=INSTRUCTIONS, version="0.2.0")

    async def call(method: str, path: str, **kwargs) -> dict:
        resp = await http.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail")
            except ValueError:
                detail = resp.text[:200]
            return {"error": f"HTTP {resp.status_code}: {detail}"}
        return resp.json()

    @server.tool()
    async def check_message(text: str, sender: str | None = None, language: Literal["en", "ur", "roman"] = "en") -> dict:
        """Check a message someone received (SMS, WhatsApp, email text) for scam signs.

        Returns the rule book's verdict (likely_scam, suspicious or no_red_flags), the reasons and what to do next.
        `sender` is who it came from, e.g. "8171", "HBL" or a phone number.
        """
        result = await call("POST", "/api/analyze", json={"text": text[:4000], "sender": sender, "language": language})
        return result if "error" in result else _short(result)

    @server.tool()
    async def lookup(value: str) -> dict:
        """Look up a phone number, website or bank account in Hoshiyar's reviewed scam reports and watchlist."""
        result = await call("POST", "/api/lookup", json={"value": value[:500]})
        if "error" in result:
            return result
        return {"kind": result["kind"], "status": result["status"], "message": result["message"]["en"],
                "confirmed_reports": result["confirmed_reports"]}

    @server.tool()
    async def recent_campaigns() -> dict:
        """Scam campaigns seen recently: groups of reports that share a website, number or wording."""
        result = await call("GET", "/api/campaigns")
        return result if "error" in result else {"campaigns": [
            {"label": c["label"], "reports": c["report_count"], "last_seen": c["last_seen"],
             "domains": [i["value"] for i in c.get("indicators", []) if i["kind"] == "domain"]}
            for c in result.get("campaigns", [])]}

    @server.tool()
    async def reporting_channels() -> dict:
        """Official places in Pakistan to report scams (NCCIA, PTA, FIA, State Bank, BISP, BEOE...)."""
        return await call("GET", "/api/channels")

    return server


def main() -> None:
    create_server().run("stdio")


if __name__ == "__main__":
    main()

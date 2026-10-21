"""Application settings, read from environment variables or a .env file."""

import logging
import re
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Values pasted into a hosting dashboard often carry a trailing newline or space; strip them.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore",
                                      str_strip_whitespace=True)

    app_env: Literal["development", "production", "test"] = "development"
    # Comma-separated list of frontend origins allowed to call the API.
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Language models -------------------------------------------------
    # auto = Groq if GROQ_API_KEY is set, else Gemini if GOOGLE_API_KEY is set, else rules only.
    llm_provider: Literal["auto", "groq", "gemini", "none"] = "auto"
    groq_api_key: str | None = None
    # Groq retired llama-3.3-70b-versatile for free keys on 2026-08-16; gpt-oss-120b is its replacement.
    groq_model: str = "openai/gpt-oss-120b"
    # A second, smaller Groq model with its own free quota. The tool-calling agents use it first.
    # Leave empty to switch it off.
    groq_fast_model: str | None = "openai/gpt-oss-20b"
    groq_reasoning_effort: Literal["low", "medium", "high"] = "low"
    # At start-up, replace a configured model the key can no longer use with a current one.
    model_autoselect: bool = True
    groq_whisper_model: str = "whisper-large-v3-turbo"
    google_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_vision_model: str = "gemini-3.5-flash-lite"
    llm_timeout_seconds: float = 25.0

    # auto = Gemini embeddings if GOOGLE_API_KEY is set, else a local hashing embedder.
    embeddings_provider: Literal["auto", "gemini", "local"] = "auto"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dims: int = 768
    # Cosine similarity needed to count a stored report as "similar".
    similarity_threshold_local: float = 0.40
    # Chosen with eval/calibrate_memory.py (no false matches on legitimate messages at 0.90).
    similarity_threshold_gemini: float = 0.90

    # Let the investigator agent decide which tools to call (needs an LLM).
    agent_investigator: bool = True
    agent_max_tool_rounds: int = 3

    # --- Storage ---------------------------------------------------------
    # Postgres URL (e.g. Neon). Empty = SQLite file + in-memory agent memory.
    database_url: str | None = None
    sqlite_path: str = "./hoshiyar.db"
    seed_demo_data: bool = True
    # Cache model readings of identical (redacted) messages so repeated scams cost no quota.
    ai_cache: bool = True
    ai_cache_days: int = 7

    # --- Link checks -----------------------------------------------------
    enable_network_checks: bool = True
    safe_browsing_api_key: str | None = None
    new_domain_days: int = 90
    http_timeout_seconds: float = 4.0

    # --- Telegram --------------------------------------------------------
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    # Channel or group for the weekly warning, e.g. @hoshiyar_alerts or -1001234567890.
    telegram_alert_chat_id: str | None = None
    # Public address of the website, used in Telegram messages (optional).
    public_app_url: str = ""

    # --- Review panel, scheduled jobs and integrations -------------------
    # Signs login tokens for analysts and admins. Set a long random string in production.
    auth_secret: str = "dev-only-auth-secret-change-me"
    token_hours: int = 12
    # First admin account, created at start-up if there are no users yet.
    admin_email: str | None = None
    admin_password: str | None = None
    # Shared secret for /api/cron/* (weekly alert, data purge), sent as the X-Cron-Secret header.
    cron_secret: str | None = None
    # Lets the browser extension and MCP server skip the captcha (header X-Hoshiyar-Key).
    integration_key: str | None = None
    # Cloudflare Turnstile secret key. When set, web checks need a captcha token.
    turnstile_secret: str | None = None

    # --- Community memory --------------------------------------------------
    # A phone number or account counts as "reported" once a reviewer approved a report with it,
    # or once this many different Telegram accounts reported it. Browser ids cost nothing to fake,
    # so they never count on their own (protects against planting a victim's number).
    min_independent_reporters: int = 2

    # --- Data retention (days) --------------------------------------------
    retention_analyses_days: int = 180
    retention_rejected_days: int = 30
    retention_pending_days: int = 90
    retention_alerts_days: int = 365
    retention_receipts_days: int = 90

    # --- Privacy and limits ----------------------------------------------
    # Secret used to fingerprint phone numbers (HMAC) so raw numbers are never stored.
    fingerprint_secret: str = "dev-only-change-me"
    rate_limit_per_minute: int = 20
    # Finding the real client address for rate limits. On Render, Cloudflare sits in front and sets
    # CF-Connecting-IP to the visitor (a client cannot forge it through Cloudflare). Without that
    # header, X-Forwarded-For is read counting this many entries from the end: on Render it ends with
    # [visitor, Cloudflare edge, Render hop], so 3. 0 = ignore both headers.
    client_ip_header: str = "cf-connecting-ip"
    trusted_proxy_hops: int = 3
    max_text_chars: int = 4000
    max_image_mb: float = 5.0
    max_audio_mb: float = 10.0
    max_pdf_mb: float = 5.0
    max_pdf_pages: int = 10
    max_email_kb: int = 512

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def resolved_llm_provider(self) -> Literal["groq", "gemini", "none"]:
        if self.llm_provider == "groq":
            return "groq" if self.groq_api_key else "none"
        if self.llm_provider == "gemini":
            return "gemini" if self.google_api_key else "none"
        if self.llm_provider == "none":
            return "none"
        if self.groq_api_key:
            return "groq"
        if self.google_api_key:
            return "gemini"
        return "none"

    @property
    def resolved_embeddings_provider(self) -> Literal["gemini", "local"]:
        if self.embeddings_provider == "local":
            return "local"
        if self.embeddings_provider == "gemini":
            return "gemini" if self.google_api_key else "local"
        return "gemini" if self.google_api_key else "local"

    @property
    def similarity_threshold(self) -> float:
        if self.resolved_embeddings_provider == "gemini":
            return self.similarity_threshold_gemini
        return self.similarity_threshold_local

    @property
    def uses_postgres(self) -> bool:
        return bool(self.database_url)

    @field_validator("database_url")
    @classmethod
    def _clean_database_url(cls, value: str | None) -> str | None:
        """Remove whitespace a paste can leave inside the URL, and use Neon's direct endpoint.

        The app keeps its own connection pool and the LangGraph checkpointer needs a real session,
        so Neon's "-pooler" host (PgBouncer in transaction mode) is swapped for the direct host.
        """
        if not value:
            return None
        url = re.sub(r"\s+", "", value)
        direct = re.sub(r"(@[^/?#]*?)-pooler(\.[^/?#]*neon\.tech)", r"\1\2", url)
        if direct != url:
            log.warning("DATABASE_URL uses Neon's -pooler host; connecting to the direct host instead.")
        return direct


@lru_cache
def get_settings() -> Settings:
    return Settings()

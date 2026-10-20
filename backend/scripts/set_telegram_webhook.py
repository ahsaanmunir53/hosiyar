"""Point your Telegram bot at the deployed backend.

Usage:
    python scripts/set_telegram_webhook.py https://your-backend.onrender.com

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET from .env.
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    base = sys.argv[1].rstrip("/")
    s = Settings()
    if not s.telegram_bot_token:
        sys.exit("TELEGRAM_BOT_TOKEN is not set in .env")
    payload = {
        "url": f"{base}/api/telegram/webhook",
        "allowed_updates": ["message", "edited_message"],
        "drop_pending_updates": True,
    }
    if s.telegram_webhook_secret:
        payload["secret_token"] = s.telegram_webhook_secret
    r = httpx.post(f"https://api.telegram.org/bot{s.telegram_bot_token}/setWebhook", json=payload, timeout=20)
    print(r.json())


if __name__ == "__main__":
    main()

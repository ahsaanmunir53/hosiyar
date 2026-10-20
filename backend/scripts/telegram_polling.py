"""Run the Telegram bot against your LOCAL backend, without a public URL.

Telegram cannot reach localhost, so this script long-polls Telegram for new messages
and forwards each one to the local webhook endpoint.

Usage (backend already running on port 8000):
    python scripts/telegram_polling.py
"""

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings  # noqa: E402

LOCAL = "http://127.0.0.1:8000/api/telegram/webhook"


def main() -> None:
    s = Settings()
    if not s.telegram_bot_token:
        sys.exit("TELEGRAM_BOT_TOKEN is not set in .env")
    api = f"https://api.telegram.org/bot{s.telegram_bot_token}"
    httpx.post(f"{api}/deleteWebhook", timeout=20)  # polling and webhooks cannot run together
    headers = {"X-Telegram-Bot-Api-Secret-Token": s.telegram_webhook_secret} if s.telegram_webhook_secret else {}
    offset = 0
    print("Polling Telegram. Send your bot a message. Ctrl+C to stop.")
    with httpx.Client(timeout=40) as client:
        while True:
            try:
                updates = client.get(f"{api}/getUpdates", params={"offset": offset, "timeout": 30}).json()
                for update in updates.get("result", []):
                    offset = update["update_id"] + 1
                    client.post(LOCAL, json=update, headers=headers)
            except httpx.HTTPError as exc:
                print("network error, retrying:", exc)
                time.sleep(3)


if __name__ == "__main__":
    main()

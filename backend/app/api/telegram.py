"""Telegram bot: forward a suspicious message, screenshot or voice note to get a verdict.

Telegram calls the webhook; we answer 200 immediately and send the reply in the background,
so slow model calls never make Telegram retry the update.
"""

import html
import logging
import re

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.ai.media import MediaUnavailable, audio_to_text, image_to_text
from app.api.service import run_analysis, run_followup, telegram_user_hash, to_response
from app.intel import family
from app.memory import store as memory

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram")

VERDICT_BADGE = {
    "likely_scam": {"en": "🔴 Likely scam", "ur": "🔴 غالباً فراڈ", "roman": "🔴 Ghaliban fraud"},
    "suspicious": {"en": "🟠 Suspicious", "ur": "🟠 مشکوک", "roman": "🟠 Mashkook"},
    "no_red_flags": {"en": "🟢 No red flags found", "ur": "🟢 کوئی خطرے کی علامت نہیں ملی", "roman": "🟢 Koi khatre ki alamat nahi mili"},
}
LABELS = {
    "why": {"en": "Why", "ur": "وجوہات", "roman": "Wajah"},
    "do": {"en": "What to do", "ur": "اب کیا کریں", "roman": "Ab kya karein"},
    "ask": {
        "en": "You can ask me about this message, e.g. \"what should I do?\" or \"I already sent money\".",
        "ur": "آپ اس پیغام کے بارے میں سوال پوچھ سکتے ہیں، مثلاً \"اب کیا کروں؟\"",
        "roman": "Aap is message ke baare mein sawal pooch sakte hain, maslan \"ab kya karun?\"",
    },
}
WELCOME = (
    "<b>Hoshiyar</b> · ہوشیار\n\n"
    "Forward me a suspicious SMS or WhatsApp message, or send a screenshot or voice note. "
    "I'll tell you if it looks like a scam and what to do.\n\n"
    "Mujhe koi bhi mashkook message, screenshot ya voice note bhejein.\n\n"
    "/urdu · /roman · /english to choose the reply language\n"
    "/share_on to share your checks (personal details removed) so reviewers can add them to the scam memory, /share_off to stop.\n"
    "/family to get a code for a relative, who sends /guard CODE here to get an alert when you receive a likely scam. "
    "/family_off stops it; a relative stops with /unguard.\n\n"
    "Personal details such as phone and card numbers are removed before anything is analysed or stored."
)
_QUESTION = re.compile(
    r"(\?|؟|\b(what|how|should|kya|kaise|kyun|kahan|ab|karun|karoon|report|shikayat|bhej diye|bata diya)\b)", re.I
)


class Telegram:
    def __init__(self, token: str, client: httpx.AsyncClient):
        self.base = f"https://api.telegram.org/bot{token}"
        self.file_base = f"https://api.telegram.org/file/bot{token}"
        self.client = client

    async def send(self, chat_id: int, text: str) -> None:
        await self.client.post(
            f"{self.base}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True},
        )

    async def typing(self, chat_id: int) -> None:
        await self.client.post(f"{self.base}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})

    async def download(self, file_id: str) -> tuple[bytes, str]:
        meta = (await self.client.get(f"{self.base}/getFile", params={"file_id": file_id})).json()
        path = meta["result"]["file_path"]
        resp = await self.client.get(f"{self.file_base}/{path}")
        resp.raise_for_status()
        return resp.content, path.rsplit("/", 1)[-1]


def format_result(result: dict, lang: str) -> str:
    e = html.escape
    lines = [f"<b>{VERDICT_BADGE[result['verdict']][lang]}</b> · {result['score']}/100", "", e(result["explanation"]["text"])]
    reasons = [r for r in result["reasons"] if r["weight"] > 0][:4]
    if reasons:
        lines += ["", f"<b>{LABELS['why'][lang]}</b>"] + [f"• {e(r['title'][lang])}" for r in reasons]
    steps = result["next_steps"][:3]
    if steps:
        lines += ["", f"<b>{LABELS['do'][lang]}</b>"] + [f"• {e(s['text'][lang])}" for s in steps]
    lines += ["", f"<i>{LABELS['ask'][lang]}</i>"]
    return "\n".join(lines)


async def handle_update(app, update: dict) -> None:
    settings = app.state.settings
    tg = Telegram(settings.telegram_bot_token, app.state.deps.http or httpx.AsyncClient(timeout=20))
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    chat_id = message["chat"]["id"]
    uhash = telegram_user_hash(settings, chat_id)
    store = app.state.deps.store
    profile = await memory.get_user_profile(store, uhash)
    lang = profile.get("language")
    text = (message.get("text") or message.get("caption") or "").strip()

    command = text.split()[0].lower().split("@", 1)[0] if text.startswith("/") else None
    if command in ("/start", "/help"):
        await tg.send(chat_id, WELCOME)
        return
    if command in ("/urdu", "/roman", "/english"):
        chosen = {"/urdu": "ur", "/roman": "roman", "/english": "en"}[command]
        await memory.update_user_profile(store, uhash, language=chosen)
        await tg.send(chat_id, {"ur": "ٹھیک ہے، اب جواب اردو میں ملیں گے۔", "roman": "Theek hai, ab jawab Roman Urdu mein milenge.", "en": "Okay, I'll reply in English."}[chosen])
        return
    if command in ("/share_on", "/share_off"):
        await memory.update_user_profile(store, uhash, share=command == "/share_on")
        await tg.send(chat_id, "Community sharing is on. Thank you." if command == "/share_on" else "Community sharing is off.")
        return
    sessionmaker = app.state.deps.sessionmaker
    if command == "/family":
        code = await family.create_code(sessionmaker, uhash)
        await tg.send(chat_id, (
            f"Your family code: <b>{code}</b> (valid for {family.CODE_HOURS} hours).\n\n"
            f"Ask a relative to open this bot and send <code>/guard {code}</code>. When one of your checks looks like "
            "a scam, they get a short alert with the scam type only, never your message.\n\n"
            f"Apne kisi rishtedar ko yeh bot khol kar <code>/guard {code}</code> bhejne ko kahein."))
        return
    if command == "/guard":
        parts = text.split()
        ok = len(parts) > 1 and await family.link_guardian(sessionmaker, parts[1], str(chat_id))
        await tg.send(chat_id, "Linked. You will get an alert when your family member receives a likely scam. /unguard to stop."
                      if ok else "That code is not valid or has expired. Ask for a new one with /family.")
        return
    if command == "/unguard":
        n = await family.remove_guardian(sessionmaker, str(chat_id))
        await tg.send(chat_id, "Family alerts stopped." if n else "You were not receiving family alerts.")
        return
    if command == "/family_off":
        n = await family.remove_member(sessionmaker, uhash)
        await tg.send(chat_id, "Family alerts for your checks are off." if n else "No family alerts were set up.")
        return

    await tg.typing(chat_id)
    thread_id = f"tg-{uhash}"
    source_kind = "text"
    try:
        if message.get("photo"):
            data, _ = await tg.download(message["photo"][-1]["file_id"])
            text = "\n".join(p for p in (await image_to_text(settings, data, "image/jpeg"), text) if p)
            source_kind = "image"
        elif message.get("voice") or message.get("audio"):
            media = message.get("voice") or message.get("audio")
            data, name = await tg.download(media["file_id"])
            text = await audio_to_text(settings, data, name or "voice.ogg")
            source_kind = "audio"
    except MediaUnavailable as exc:
        await tg.send(chat_id, html.escape(str(exc)) + " Please paste the text instead.")
        return
    except Exception:
        log.exception("telegram media download failed")
        await tg.send(chat_id, "I couldn't read that file. Please paste the message text instead.")
        return

    if not text:
        await tg.send(chat_id, WELCOME)
        return

    graph = app.state.graph
    previous = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    is_followup = (
        source_kind == "text"
        and previous
        and previous.values.get("verdict")
        and len(text) < 160
        and "http" not in text.lower()
        and _QUESTION.search(text)
        and not message.get("forward_origin")
    )
    try:
        if is_followup:
            answer = await run_followup(graph, thread_id, question=text, user_hash=uhash, requested_language=lang)
            await tg.send(chat_id, html.escape(answer["answer"]))
            return
        _, state = await run_analysis(
            graph,
            thread_id=thread_id,
            text=text,
            sender=None,
            share=bool(profile.get("share")),
            requested_language=lang,
            user_hash=uhash,
            channel="telegram",
            source_kind=source_kind,
        )
        result = to_response(thread_id, state)
        await tg.send(chat_id, format_result(result, result["language"]))
    except Exception:
        log.exception("telegram analysis failed")
        await tg.send(chat_id, "Something went wrong while checking this message. Please try again in a minute.")


@router.post("/webhook")
async def webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    settings = request.app.state.settings
    if not settings.telegram_bot_token:
        raise HTTPException(404, "Telegram is not configured.")
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(401, "Bad secret token.")
    update = await request.json()
    background.add_task(handle_update, request.app, update)
    return {"ok": True}

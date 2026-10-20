"""Explanations and follow-up answers: templates always, the language model when available."""

import asyncio
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import text_of
from app.ai.model_status import note_failure, note_success
from app.ai.prompts import EXPLAIN_SYSTEM, FOLLOWUP_SYSTEM, LANGUAGE_NAMES
from app.ai.signals import short_error
from app.core.text import normalize
from app.guidance.next_steps import channels
from app.rules.engine import CATEGORY_LABELS

log = logging.getLogger(__name__)

HEADLINES = {
    "likely_scam": {
        "en": "This looks like a scam.",
        "ur": "یہ پیغام فراڈ لگتا ہے۔",
        "roman": "Yeh message fraud lagta hai.",
    },
    "suspicious": {
        "en": "Be careful. This message has warning signs.",
        "ur": "احتیاط کریں، اس پیغام میں خطرے کی علامات ہیں۔",
        "roman": "Ehtiyat karein, is message mein khatre ki alamat hain.",
    },
    "no_red_flags": {
        "en": "We found no common scam signs.",
        "ur": "ہمیں عام فراڈ کی کوئی علامت نہیں ملی۔",
        "roman": "Humein aam fraud ki koi alamat nahi mili.",
    },
}

NOT_PROOF = {
    "en": "That does not prove it is genuine. If in doubt, contact the organisation on a number you already trust.",
    "ur": "اس کا مطلب یہ نہیں کہ پیغام یقینی طور پر اصلی ہے۔ شک ہو تو ادارے سے اس نمبر پر رابطہ کریں جو آپ کو پہلے سے معلوم ہو۔",
    "roman": "Is ka matlab yeh nahi ke message yaqeenan asli hai. Shak ho to idaray se us number par rabta karein jo aap ko pehle se maloom ho.",
}


def template_explanation(verdict: str, hits: list[dict]) -> dict[str, str]:
    out = {}
    positive = [h for h in hits if h["weight"] > 0]
    for lang in ("en", "ur", "roman"):
        parts = [HEADLINES[verdict][lang]]
        if verdict == "no_red_flags":
            parts.append(NOT_PROOF[lang])
        else:
            for h in positive[:2]:
                parts.append(h["why"][lang])
        out[lang] = " ".join(parts)
    return out


_CONTRADICTIONS = {
    "likely_scam": r"\b(is safe|is genuine|is legitimate|not a scam|no scam|looks real|safe hai|asli hai|fraud nahi)\b|محفوظ ہے|اصلی ہے|فراڈ نہیں",
    "suspicious": r"\b(definitely safe|completely safe|100% safe|bilkul safe|is safe|is genuine|is a scam|likely a scam|definitely a scam|yaqeenan fraud)\b|بالکل محفوظ|یقیناً فراڈ",
    "no_red_flags": r"\b(is a scam|definitely a scam|yeh fraud hai|ye fraud hai)\b|یہ فراڈ ہے",
}


def contradicts(verdict: str, text: str) -> bool:
    return bool(re.search(_CONTRADICTIONS[verdict], normalize(text)))


def _result_brief(state: dict, language: str) -> str:
    lines = [
        f"Verdict (fixed): {state['verdict']}",
        f"Score: {state['score']}/100",
        f"Category: {CATEGORY_LABELS.get(state['category'], CATEGORY_LABELS['other'])['en']}",
        "Reasons:",
    ]
    for h in state.get("rule_hits", [])[:6]:
        if h["weight"] > 0:
            lines.append(f"- {h['title']['en']}: {h['why']['en']}")
    if state.get("memory_matches"):
        lines.append(f"Similar known scams found: {len(state['memory_matches'])}")
    return "\n".join(lines)


async def ai_explanation(llm: BaseChatModel, state: dict, language: str, timeout: float) -> str | None:
    prompt = EXPLAIN_SYSTEM.format(language_name=LANGUAGE_NAMES[language])
    message = (
        f"Message (personal details removed):\n\"\"\"\n{state['redacted_text'][:1500]}\n\"\"\"\n\n"
        f"{_result_brief(state, language)}"
    )
    try:
        result = await asyncio.wait_for(llm.ainvoke([SystemMessage(prompt), HumanMessage(message)]), timeout)
        note_success(llm)
    except Exception as exc:
        note_failure(llm, exc)
        log.warning("explanation failed: %s", short_error(exc))
        return None
    text = text_of(result).strip()
    if not text or contradicts(state["verdict"], text):
        return None
    words = text.split()
    return " ".join(words[:110])


# --- Follow-up questions ------------------------------------------------------

_INTENTS = [
    ("money_sent", r"\b(sent (the )?money|paid|transfer(red)? (kar|kr) (diya|dia|di)|paise bhej (diye|diya|dye|di)|bhej (chuka|chuki|diye)|payment kar (di|diya))\b|پیسے بھیج دیے|رقم بھیج دی"),
    ("code_shared", r"\b(shared (the )?(code|otp|pin)|gave (the )?(code|otp)|code (bata|de|bhej) (diya|dia|di)|otp (bata|de|bhej) (diya|dia|di))\b|کوڈ بتا دیا|کوڈ بھیج دیا"),
    ("report", r"\b(report|complain|complaint|shikayat|shikait|kahan bataun|kahan report)\b|شکایت|رپورٹ"),
    ("why", r"\b(why|kyun|kyon|kiun|kis wajah|kaise pata)\b|کیوں"),
    ("safe", r"\b(safe|click|open|khol|kholun|reply|jawab doon|call kar)\w*\b|محفوظ|کھول"),
]

_CANNED = {
    "money_sent": {
        "en": "Act now: call your bank or wallet on the number printed on your card or in its official app and ask them to block the transaction. Then file a complaint with NCCIA at nccia.gov.pk and keep screenshots and the transaction ID.",
        "ur": "فوراً اپنے بینک یا والیٹ کو کارڈ کے پیچھے لکھے یا ایپ میں دیے گئے نمبر پر کال کریں اور ٹرانزیکشن روکنے کو کہیں۔ پھر nccia.gov.pk پر شکایت درج کریں اور اسکرین شاٹ اور ٹرانزیکشن آئی ڈی سنبھال کر رکھیں۔",
        "roman": "Foran apne bank ya wallet ko card ke peeche likhe ya app mein diye gaye number par call karein aur transaction rokne ko kahein. Phir nccia.gov.pk par shikayat darj karein aur screenshots aur transaction ID sambhal kar rakhein.",
    },
    "code_shared": {
        "en": "Change your passwords and PINs now, turn on WhatsApp two-step verification (Settings > Account > Two-step verification), and call your bank or wallet if the code was for them. Tell your contacts not to trust money requests from your number for a while.",
        "ur": "ابھی اپنے پاس ورڈ اور پن بدلیں، واٹس ایپ میں ٹو اسٹیپ ویریفکیشن آن کریں، اور اگر کوڈ بینک یا والیٹ کا تھا تو انہیں کال کریں۔ اپنے رابطوں کو بتائیں کہ کچھ دن آپ کے نمبر سے پیسوں کی درخواست پر بھروسہ نہ کریں۔",
        "roman": "Abhi apne password aur PIN badlein, WhatsApp mein two-step verification on karein, aur agar code bank ya wallet ka tha to unhein call karein. Apne contacts ko batayen ke kuch din aap ke number se paison ki request par bharosa na karein.",
    },
    "report": {
        "en": "Report online fraud to NCCIA at nccia.gov.pk, and report the number to PTA at complaint.pta.gov.pk or 0800-55055 so the SIM can be blocked.",
        "ur": "آن لائن فراڈ کی شکایت nccia.gov.pk پر کریں، اور نمبر کو پی ٹی اے کو complaint.pta.gov.pk یا 0800-55055 پر رپورٹ کریں تاکہ سم بند ہو سکے۔",
        "roman": "Online fraud ki shikayat nccia.gov.pk par karein, aur number ko PTA ko complaint.pta.gov.pk ya 0800-55055 par report karein taake SIM band ho sake.",
    },
    "safe_risky": {
        "en": "No. Do not open the link, reply or call the number in this message. If you want to check, contact the organisation using its official app or the number on your card.",
        "ur": "نہیں۔ اس پیغام کا لنک نہ کھولیں، جواب نہ دیں اور دیا گیا نمبر نہ ملائیں۔ تصدیق کرنی ہو تو ادارے کی سرکاری ایپ یا کارڈ والے نمبر سے رابطہ کریں۔",
        "roman": "Nahi. Is message ka link na kholein, jawab na dein aur diya gaya number na milayen. Tasdeeq karni ho to idaray ki official app ya card wale number se rabta karein.",
    },
    "safe_clear": {
        "en": "We found no common scam signs, but that is not a guarantee. If it asks for codes or money later, stop and check with the organisation directly.",
        "ur": "ہمیں عام فراڈ کی علامات نہیں ملیں، لیکن یہ ضمانت نہیں۔ اگر بعد میں کوڈ یا پیسے مانگے جائیں تو رک جائیں اور ادارے سے براہ راست تصدیق کریں۔",
        "roman": "Humein aam fraud ki alamat nahi milin, lekin yeh guarantee nahi. Agar baad mein code ya paise mange jayen to ruk jayen aur idaray se seedha tasdeeq karein.",
    },
    "no_context": {
        "en": "Send me the message you want checked first, then ask your question.",
        "ur": "پہلے وہ پیغام بھیجیں جسے چیک کرنا ہے، پھر سوال پوچھیں۔",
        "roman": "Pehle woh message bhejein jise check karna hai, phir sawal poochein.",
    },
}


def canned_answer(state: dict, question: str, language: str) -> str:
    if not state.get("verdict"):
        return _CANNED["no_context"][language]
    q = normalize(question)
    intent = next((name for name, pat in _INTENTS if re.search(pat, q)), None)
    if intent == "money_sent":
        return _CANNED["money_sent"][language]
    if intent == "code_shared":
        return _CANNED["code_shared"][language]
    if intent == "report":
        return _CANNED["report"][language]
    if intent == "safe":
        return _CANNED["safe_clear" if state["verdict"] == "no_red_flags" else "safe_risky"][language]
    if intent == "why":
        reasons = [h["title"][language] for h in state.get("rule_hits", []) if h["weight"] > 0][:3]
        if reasons:
            sep, end = ("، ", "۔") if language == "ur" else ("; ", ".")
            return f"{HEADLINES[state['verdict']][language]} {sep.join(reasons)}{end}"
        return template_explanation(state["verdict"], [])[language]
    steps = [s["text"][language] for s in state.get("next_steps", [])[:3]]
    return " ".join(steps) or template_explanation(state["verdict"], state.get("rule_hits", []))[language]


async def ai_followup(llm: BaseChatModel, state: dict, question: str, language: str, timeout: float) -> str | None:
    ch = channels()
    channel_lines = "\n".join(
        f"- {c['name']}: {c.get('url', '')} {c.get('phone', '')} ({c['for']})" for c in ch.values()
    )
    history = "\n".join(f"Q: {f['question']}\nA: {f['answer']}" for f in state.get("followups", [])[-3:])
    content = (
        f"{_result_brief(state, language)}\n\nNext steps already shown:\n"
        + "\n".join(f"- {s['text']['en']}" for s in state.get("next_steps", []))
        + f"\n\nOfficial channels:\n{channel_lines}\n\nEarlier questions:\n{history or '(none)'}\n\nQuestion: {question[:500]}"
    )
    try:
        result = await asyncio.wait_for(
            llm.ainvoke([SystemMessage(FOLLOWUP_SYSTEM.format(language_name=LANGUAGE_NAMES[language])), HumanMessage(content)]),
            timeout,
        )
        note_success(llm)
    except Exception as exc:
        note_failure(llm, exc)
        log.warning("follow-up failed: %s", short_error(exc))
        return None
    text = text_of(result).strip()
    if not text or contradicts(state["verdict"], text):
        return None
    return " ".join(text.split()[:110])

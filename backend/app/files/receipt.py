"""Experimental: check a "payment sent" screenshot someone shows you.

Fake JazzCash, Easypaisa and bank-transfer receipts are made with editing apps to trick
sellers. A screenshot can never prove a payment, so this check gives no verdict. It reads the
receipt with Gemini, runs a few deterministic consistency checks, and always gives the one
reliable advice: confirm in your own app. Nothing is stored.
"""

import base64
import json
import re
from datetime import UTC, datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import text_of
from app.ai.media import MediaUnavailable
from app.config import Settings

PROMPT = """You read a screenshot of a mobile-wallet or bank payment receipt. Report only what is visible.
Return one JSON object with these keys (use null when not visible):
app_name, status_text, amount_text, currency, date_text, time_text, transaction_id, sender_name,
sender_account_masked, receiver_name, receiver_account_masked, fee_text,
visual_issues (a list of short, concrete observations such as "digits in the amount use two different fonts",
"text is not aligned with the rest of the line", "status bar time differs from receipt time"; empty if none).
Do not guess. Do not say whether the receipt is real."""

_DATE_FORMATS = ("%d-%b-%Y", "%d %b %Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%b %d, %Y", "%d %B %Y", "%B %d, %Y", "%d.%m.%Y")
_AMOUNT_OK = re.compile(r"^\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?$|^\d+(?:\.\d{1,2})?$")


def _t(en: str, ur: str, roman: str) -> dict:
    return {"en": en, "ur": ur, "roman": roman}


ADVICE = [
    _t("A screenshot is not proof of payment. Open your own JazzCash, Easypaisa or bank app and check that the money has actually arrived in your balance before handing anything over.",
       "اسکرین شاٹ ادائیگی کا ثبوت نہیں۔ کچھ دینے سے پہلے اپنی جاز کیش، ایزی پیسہ یا بینک ایپ کھول کر دیکھیں کہ رقم واقعی آپ کے بیلنس میں آ گئی ہے۔",
       "Screenshot payment ka saboot nahi. Kuch dene se pehle apni JazzCash, Easypaisa ya bank app khol kar dekhein ke raqam waqai aap ke balance mein aa gayi hai."),
    _t("Do not trust an SMS that says money was received either. Check the transaction in the app itself.",
       "رقم ملنے کے ایس ایم ایس پر بھی بھروسہ نہ کریں۔ ٹرانزیکشن خود ایپ میں چیک کریں۔",
       "Raqam milne ke SMS par bhi bharosa na karein. Transaction khud app mein check karein."),
    _t("If someone says they sent too much by mistake and asks you to return the difference, check your balance first. This is a common trick.",
       "اگر کوئی کہے کہ غلطی سے زیادہ پیسے بھیج دیے، فرق واپس کریں، تو پہلے اپنا بیلنس چیک کریں۔ یہ عام چال ہے۔",
       "Agar koi kahe ke ghalti se zyada paise bhej diye, farq wapas karein, to pehle apna balance check karein. Yeh aam chaal hai."),
]


_DATE_PART = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d{1,2}[-/. ](?:\d{1,2}|[A-Za-z]{3,9})[-/. ]\d{4}|[A-Za-z]{3,9} \d{1,2}, \d{4}|\d{1,2} [A-Za-z]{3,9} \d{4}"
)


def _parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    m = _DATE_PART.search(text)
    if not m:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(m.group(0), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def normalize_fields(raw: dict) -> dict:
    """Model output can be off-shape: scalars must be short strings, visual_issues a list of strings."""
    out: dict = {}
    for key, value in raw.items():
        if key == "visual_issues":
            items = value if isinstance(value, list) else []
            out[key] = [str(x)[:160] for x in items if isinstance(x, (str, int, float)) and str(x).strip()][:6]
        elif isinstance(value, (str, int, float)):
            out[str(key)[:40]] = str(value)[:200]
        elif isinstance(value, list):
            out[str(key)[:40]] = ", ".join(str(x) for x in value if isinstance(x, (str, int, float)))[:200] or None
        else:
            out[str(key)[:40]] = None
    return out


def consistency_findings(fields: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    findings: list[dict] = []
    status = (fields.get("status_text") or "").lower()
    if status and re.search(r"pending|processing|failed|unsuccessful|in progress|reversed", status):
        findings.append({"id": "status", "severity": "high", "text": _t(
            f"The receipt itself says \"{fields.get('status_text')}\", not successful.",
            f"رسید پر خود \"{fields.get('status_text')}\" لکھا ہے، کامیاب نہیں۔",
            f"Raseed par khud \"{fields.get('status_text')}\" likha hai, kamyab nahi.")})
    if not fields.get("transaction_id"):
        findings.append({"id": "no_reference", "severity": "medium", "text": _t(
            "No transaction ID or reference number is visible. Genuine receipts show one.",
            "کوئی ٹرانزیکشن آئی ڈی یا ریفرنس نمبر نظر نہیں آتا۔ اصلی رسید پر یہ ہوتا ہے۔",
            "Koi transaction ID ya reference number nazar nahi aata. Asli raseed par yeh hota hai.")})
    amount = re.sub(r"(?i)rs\.?|pkr|/-|\s", "", fields.get("amount_text") or "")
    if amount and not _AMOUNT_OK.match(amount):
        findings.append({"id": "amount_format", "severity": "medium", "text": _t(
            f"The amount \"{fields.get('amount_text')}\" is written in an unusual way (check the commas and digits).",
            f"رقم \"{fields.get('amount_text')}\" غیر معمولی انداز میں لکھی ہے (کاما اور ہندسے دیکھیں)۔",
            f"Raqam \"{fields.get('amount_text')}\" ghair mamooli andaaz mein likhi hai (comma aur digits dekhein).")})
    when = _parse_date(fields.get("date_text"))
    if when and when > now + timedelta(days=1):
        findings.append({"id": "future_date", "severity": "high", "text": _t(
            f"The date on the receipt ({fields.get('date_text')}) is in the future.",
            f"رسید پر تاریخ ({fields.get('date_text')}) آنے والے دنوں کی ہے۔",
            f"Raseed par tareekh ({fields.get('date_text')}) aane wale dino ki hai.")})
    for issue in (fields.get("visual_issues") or [])[:4]:
        findings.append({"id": "visual", "severity": "low", "source": "ai", "text": _t(
            f"AI noticed: {issue}", f"اے آئی نے دیکھا: {issue}", f"AI ne dekha: {issue}")})
    return findings


async def read_receipt(settings: Settings, data: bytes, mime: str) -> dict:
    if not settings.google_api_key:
        raise MediaUnavailable("Reading payment screenshots needs GOOGLE_API_KEY (Gemini).")
    from app.ai.llm import gemini_chat

    model = gemini_chat(settings, settings.gemini_vision_model, retries=1)
    msg = HumanMessage(content=[
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": f"data:{mime};base64,{base64.b64encode(data).decode()}"},
    ])
    reply = await model.ainvoke([SystemMessage("You extract fields from receipts as JSON."), msg])
    match = re.search(r"\{.*\}", text_of(reply), re.S)
    try:
        raw = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        raw = {}
    fields = normalize_fields(raw if isinstance(raw, dict) else {})
    return {"experimental": True, "fields": fields, "findings": consistency_findings(fields),
            "advice": ADVICE, "model": settings.gemini_vision_model}

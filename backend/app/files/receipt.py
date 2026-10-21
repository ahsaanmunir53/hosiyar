"""Experimental: check a "payment sent" screenshot someone shows you.

Fake JazzCash, Easypaisa and bank-transfer receipts are made with editing apps to trick
sellers. A screenshot can never prove a payment, so this check gives no verdict. It reads the
receipt with Gemini, runs a few deterministic consistency checks, and always gives the one
reliable advice: confirm in your own app. Nothing is stored.
"""

import base64
import json
import re
from datetime import UTC, datetime, timedelta, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import text_of
from app.ai.media import MediaUnavailable
from app.config import Settings

PROMPT = """You read a screenshot of a mobile-wallet or bank payment receipt. Report only what is visible.
Return one JSON object with these keys (use null when not visible):
app_name, status_text, amount_text, currency, date_text, time_text, transaction_id, sender_name,
sender_account_masked, receiver_name, receiver_account_masked, fee_text,
status_bar_time (the clock in the phone's status bar at the very top of the screenshot, if one is visible),
visual_issues (a list of short, concrete observations such as "digits in the amount use two different fonts",
"text is not aligned with the rest of the line", "status bar time differs from receipt time"; empty if none).
Copy phone and account numbers exactly, character by character, including every * or x used to hide digits.
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


PKT = timezone(timedelta(hours=5))
_MASK_CHARS = "*xX•●∗#"
_TIME = re.compile(r"(\d{1,2}):(\d{2})\s*([AaPp]\.?[Mm]\.?)?")


def _longest_run(digits: str) -> int:
    """Longest stretch of digits going up by one, down by one, or repeating (1234567, 98765, 000000)."""
    best = run = 1
    step = None
    for a, b in zip(digits, digits[1:], strict=False):
        d = int(b) - int(a)
        if d in (1, -1, 0):
            run = run + 1 if d == step else 2
            step = d
        else:
            run, step = 1, None
        best = max(best, run)
    return best if digits else 0


def _number_problem(value: str | None) -> tuple[str, str] | None:
    """('length', n) for a Pakistani mobile number with the wrong length (digits plus hiding stars),
    ('placeholder', digits) for a fully visible number like 03011234567."""
    if not value:
        return None
    v = re.sub(r"[\s-]", "", value)
    v = re.sub(r"^(?:\+92|0092|92)(?=3)", "0", v)
    if not re.fullmatch(rf"03[\d{re.escape(_MASK_CHARS)}]+", v):
        return None
    if len(v) != 11:
        return ("length", str(len(v)))
    if v.isdigit() and _longest_run(v[2:]) >= 6:
        return ("placeholder", v)
    return None


def _minutes(text: str | None) -> list[int]:
    """Minutes after midnight. A 12-hour clock without AM/PM gives both readings."""
    m = _TIME.search(text or "")
    if not m:
        return []
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if hour > 23 or minute > 59:
        return []
    if ampm.startswith("p") and hour < 12:
        return [(hour + 12) * 60 + minute]
    if ampm.startswith("a"):
        return [(hour % 12) * 60 + minute]
    if hour <= 12:
        return sorted({(hour % 12) * 60 + minute, (hour % 12 + 12) * 60 + minute})
    return [hour * 60 + minute]


def assessment(findings: list[dict]) -> str:
    """likely_fake (a high finding), suspicious (a medium one) or no_signs. Never 'real'."""
    severities = {f["severity"] for f in findings if f.get("source") != "ai"}
    return "likely_fake" if "high" in severities else "suspicious" if "medium" in severities else "no_signs"


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
    when = _parse_date(fields.get("date_text")) or _parse_date(fields.get("time_text"))
    shown = fields.get("date_text") or fields.get("time_text")
    today = now.astimezone(PKT).date()
    if when and when > now + timedelta(days=1):
        findings.append({"id": "future_date", "severity": "high", "text": _t(
            f"The date on the receipt ({shown}) is in the future.",
            f"رسید پر تاریخ ({shown}) آنے والے دنوں کی ہے۔",
            f"Raseed par tareekh ({shown}) aane wale dino ki hai.")})
    elif when:
        age = (today - when.date()).days
        if age > 30:
            months = age // 30
            findings.append({"id": "old_date", "severity": "high", "text": _t(
                f"The receipt is dated {shown}, about {months} months ago. A payment someone says they just sent "
                "should show today's date; an old receipt is often reused or edited.",
                f"رسید پر تاریخ {shown} ہے، یعنی تقریباً {months} مہینے پرانی۔ جو ادائیگی ابھی بھیجی گئی ہو اس پر آج کی "
                "تاریخ ہونی چاہیے؛ پرانی رسید اکثر دوبارہ استعمال یا ایڈٹ کی جاتی ہے۔",
                f"Raseed par tareekh {shown} hai, yani taqreeban {months} mahine purani. Jo payment abhi bheji gayi ho "
                "us par aaj ki tareekh honi chahiye; purani raseed aksar dobara use ya edit ki jati hai.")})
        elif age > 2:
            findings.append({"id": "old_date", "severity": "medium", "text": _t(
                f"The receipt is dated {shown}, {age} days ago. If the payment was meant to be made today, ask why.",
                f"رسید پر تاریخ {shown} ہے، {age} دن پہلے کی۔ اگر ادائیگی آج ہونی تھی تو وجہ پوچھیں۔",
                f"Raseed par tareekh {shown} hai, {age} din pehle ki. Agar payment aaj honi thi to wajah poochein.")})
    for key, who in (("sender_account_masked", ("sender", "بھیجنے والے", "bhejne wale")),
                     ("receiver_account_masked", ("receiver", "وصول کرنے والے", "wusool karne wale"))):
        value = fields.get(key)
        problem = _number_problem(value)
        if problem and problem[0] == "length":
            findings.append({"id": "number_length", "severity": "medium", "text": _t(
                f"The {who[0]}'s number \"{value}\" has {problem[1]} characters; a Pakistani mobile number has 11. "
                "Count the digits and stars yourself; a wrong count is a common mistake in edited receipts.",
                f"{who[1]} کا نمبر \"{value}\" {problem[1]} حروف کا ہے؛ پاکستانی موبائل نمبر 11 ہندسوں کا ہوتا ہے۔ "
                "ہندسے اور ستارے خود گنیں؛ ایڈٹ کی گئی رسیدوں میں یہ عام غلطی ہے۔",
                f"{who[2].capitalize()} ka number \"{value}\" {problem[1]} characters ka hai; Pakistani mobile number 11 "
                "digits ka hota hai. Digits aur stars khud ginein; edit ki gayi raseedon mein yeh aam ghalti hai.")})
        elif problem:
            findings.append({"id": "placeholder_number", "severity": "high", "text": _t(
                f"The {who[0]}'s number \"{value}\" is a made-up looking sequence (like 1234567). Real numbers rarely look like this.",
                f"{who[1]} کا نمبر \"{value}\" بنایا ہوا لگتا ہے (جیسے 1234567)۔ اصلی نمبر ایسے کم ہی ہوتے ہیں۔",
                f"{who[2].capitalize()} ka number \"{value}\" banaya hua lagta hai (jaise 1234567). Asli number aise kam hi hote hain.")})
    bar, paid = _minutes(fields.get("status_bar_time")), _minutes(fields.get("time_text") or fields.get("date_text"))
    if bar and paid and (when is None or when.date() == today) and all(b < paid[0] - 2 for b in bar):
        findings.append({"id": "clock_before_payment", "severity": "high", "text": _t(
            f"The phone's clock in the screenshot shows {fields.get('status_bar_time')}, earlier than the payment time "
            f"{fields.get('time_text') or ''}. The screenshot seems to be taken before the payment happened.",
            f"اسکرین شاٹ میں فون کی گھڑی {fields.get('status_bar_time')} دکھا رہی ہے جو ادائیگی کے وقت سے پہلے ہے۔ "
            "لگتا ہے اسکرین شاٹ ادائیگی سے پہلے لیا گیا۔",
            f"Screenshot mein phone ki ghari {fields.get('status_bar_time')} dikha rahi hai jo payment ke waqt se pehle hai. "
            "Lagta hai screenshot payment se pehle liya gaya.")})
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
    findings = consistency_findings(fields)
    return {"experimental": True, "fields": fields, "findings": findings, "assessment": assessment(findings),
            "advice": ADVICE, "model": settings.gemini_vision_model}

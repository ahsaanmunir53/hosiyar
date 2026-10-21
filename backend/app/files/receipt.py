"""Experimental: check a "payment sent" screenshot someone shows you.

Fake JazzCash, Easypaisa and bank-transfer receipts are made with editing apps or AI image
generators to trick sellers. A screenshot can never prove a payment, so this check never says
"real". Gemini only reads the text; the decisions are deterministic:

* the receipt itself: status, date (too old, in the future, impossible, wrong weekday), time,
  amount format, total = amount + fee, amount in words, phone numbers (length, made-up sequences),
  IBAN checksum, misspelled wallet or bank name, phone clock earlier than the payment;
* the person checking: the amount they expect and their own number or account;
* the image file: AI-generator or editing-app labels in its metadata, AI-generator image sizes;
* memory: the same receipt (transaction ID and amount) checked by someone else before, or already
  found fake; numbers on the receipt that reviewers confirmed as scam numbers.

The image and the person's own number are never stored. For the memory check only a keyed hash
of the transaction ID and amount is kept (90 days), so the receipt cannot be read back from it.
"""

import base64
import json
import re
from datetime import UTC, datetime, timedelta, timezone

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import text_of
from app.config import Settings
from app.files.image_meta import AI_SIZES, inspect

PROMPT = """You read a screenshot of a mobile-wallet or bank payment receipt. Report only what is visible.
Return one JSON object with these keys (use null when not visible):
app_name, status_text, amount_text, currency, date_text, time_text, transaction_id, sender_name,
sender_account_masked, receiver_name, receiver_account_masked, fee_text,
status_bar_time (the clock in the phone's status bar at the very top of the screenshot, if one is visible),
total_text (a total or "total amount" line if shown separately from the amount), amount_in_words,
text_mistakes (a list of words on the receipt that look misspelled, copied exactly as printed),
visual_issues (a list of short, concrete observations such as "digits in the amount use two different fonts",
"text is not aligned with the rest of the line", "status bar time differs from receipt time"; empty if none).
Copy phone and account numbers exactly, character by character, including every * or x used to hide digits.
Copy names, the date (with the weekday if one is shown) and the app or bank name exactly as printed, even if misspelled.
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
    """likely_fake (a deterministic high finding), suspicious (a medium one, or two AI observations)
    or no_signs. Never 'real'. AI observations alone can never make a receipt 'likely fake'."""
    severities = {f["severity"] for f in findings if f.get("source") != "ai"}
    if "high" in severities:
        return "likely_fake"
    if "medium" in severities or sum(f.get("source") == "ai" for f in findings) >= 2:
        return "suspicious"
    return "no_signs"


def consistency_findings(fields: dict, now: datetime | None = None, expected_amount: str | None = None,
                         my_account: str | None = None) -> list[dict]:
    """Deterministic checks on what the receipt says (and on what the person expected)."""
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
    findings += _calendar_findings(fields)
    findings += _sum_findings(fields)
    findings += _iban_findings(fields)
    findings += _brand_findings(fields)
    findings += _expectation_findings(fields, expected_amount, my_account)
    for issue in (fields.get("visual_issues") or [])[:4]:
        findings.append({"id": "visual", "severity": "low", "source": "ai", "text": _t(
            f"AI noticed: {issue}", f"اے آئی نے دیکھا: {issue}", f"AI ne dekha: {issue}")})
    mistakes = (fields.get("text_mistakes") or "").strip()
    if mistakes and mistakes.lower() not in ("none", "null", "[]"):
        findings.append({"id": "spelling", "severity": "low", "source": "ai", "text": _t(
            f"AI noticed words that look misspelled: {mistakes}. Real apps do not have spelling mistakes.",
            f"اے آئی کو غلط ہجے والے الفاظ نظر آئے: {mistakes}۔ اصلی ایپس میں ہجے کی غلطیاں نہیں ہوتیں۔",
            f"AI ko ghalat spelling wale alfaz nazar aaye: {mistakes}. Asli apps mein spelling ki ghaltiyan nahi hotin.")})
    return findings


# --------------------------------------------------------------------------- calendar and clock

_MONTHS = {m: i for i, names in enumerate(
    [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
     ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
     ("dec", "december")], start=1) for m in names}
_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[-/. ]+([A-Za-z]{3,9}|\d{1,2})\.?[-/., ]+(\d{4})\b")
_MDY = re.compile(r"\b([A-Za-z]{3,9})\.? (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})\b")
_YMD = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp]\.?[Mm]\.?)?")
_WEEKDAY = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)(?:day|sday|nesday|rsday|urday)?\b\.?", re.I)


def _valid(y: int, m: int, d: int) -> bool:
    try:
        datetime(y, m, d)
        return True
    except ValueError:
        return False


def _date_candidates(text: str) -> tuple[list[tuple[int, int, int]], bool]:
    """Possible (year, month, day) readings and whether a date was written at all."""
    for rx, order in ((_YMD, "ymd"), (_MDY, "mdy"), (_DMY, "dmy")):
        m = rx.search(text)
        if not m:
            continue
        a, b, c = m.groups()
        if order == "ymd":
            return [(int(a), int(b), int(c))], True
        if order == "mdy":
            month = _MONTHS.get(a.lower())
            return ([(int(c), month, int(b))] if month else []), bool(month)
        year = int(c)
        if b.isdigit():
            # 28/10/2024 or 10/28/2024: try both orders
            return [(year, int(b), int(a)), (year, int(a), int(b))], True
        month = _MONTHS.get(b.lower())
        return ([(year, month, int(a))] if month else []), bool(month)
    return [], False


def _calendar_findings(fields: dict) -> list[dict]:
    out: list[dict] = []
    text = " ".join(str(fields.get(k) or "") for k in ("date_text", "time_text"))
    candidates, written = _date_candidates(text)
    valid = [c for c in candidates if 1 <= c[1] <= 12 and _valid(*c)]
    if written and candidates and not valid:
        out.append({"id": "impossible_date", "severity": "high", "text": _t(
            f"The date \"{fields.get('date_text')}\" does not exist on the calendar (for example 31 February).",
            f"تاریخ \"{fields.get('date_text')}\" کیلنڈر میں موجود ہی نہیں (جیسے 31 فروری)۔",
            f"Tareekh \"{fields.get('date_text')}\" calendar mein mojood hi nahi (jaise 31 February).")})
    day_name = _WEEKDAY.search(text)
    if day_name and valid:
        wanted = _WEEKDAYS[day_name.group(1).lower()]
        actual = {datetime(*c).weekday() for c in valid}
        if wanted not in actual:
            real = datetime(*valid[0]).strftime("%A")
            out.append({"id": "wrong_weekday", "severity": "high", "text": _t(
                f"The receipt says {day_name.group(0)}, but {datetime(*valid[0]).strftime('%d %b %Y')} was a {real}. "
                "Apps get the weekday right; people editing a receipt often do not.",
                f"رسید پر {day_name.group(0)} لکھا ہے، لیکن {datetime(*valid[0]).strftime('%d %b %Y')} کو {real} تھا۔ "
                "ایپ دن غلط نہیں لکھتی؛ رسید ایڈٹ کرنے والے اکثر غلطی کرتے ہیں۔",
                f"Raseed par {day_name.group(0)} likha hai, lekin {datetime(*valid[0]).strftime('%d %b %Y')} ko {real} tha. "
                "App din ghalat nahi likhti; raseed edit karne wale aksar ghalti karte hain.")})
    for key in ("time_text", "date_text", "status_bar_time"):
        m = _CLOCK.search(str(fields.get(key) or ""))
        if not m:
            continue
        hour, minute, second, ampm = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0), m.group(4)
        if hour > 23 or minute > 59 or second > 59 or (ampm and hour > 12):
            out.append({"id": "impossible_time", "severity": "high", "text": _t(
                f"The time \"{m.group(0).strip()}\" is not a real clock time.",
                f"وقت \"{m.group(0).strip()}\" اصل گھڑی کا وقت نہیں ہو سکتا۔",
                f"Waqt \"{m.group(0).strip()}\" asli ghari ka waqt nahi ho sakta.")})
            break
    return out


# --------------------------------------------------------------------------- money

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), start=2)}
_SCALES = {"thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
           "million": 1_000_000, "crore": 10_000_000, "crores": 10_000_000, "billion": 1_000_000_000}
_FILLER = {"and", "rupees", "rupee", "rs", "pkr", "only", "pak", "pakistani", "amount", "of", "the", "sum"}


def money(text: str | None) -> float | None:
    m = _NUMBER.search((text or "").replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def words_to_number(text: str | None) -> int | None:
    """'Two Thousand Three Hundred Fifty Rupees Only' -> 2350. None when a word is not a number word."""
    words = re.findall(r"[a-z]+", (text or "").lower().replace("-", " "))
    if {"paisa", "paise", "paisas", "point"} & set(words):
        return None  # fractions are written too many ways to judge safely
    total = current = 0
    seen = False
    for w in words:
        if w in _FILLER:
            continue
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = (current or 1) * 100
        elif w in _SCALES:
            total += (current or 1) * _SCALES[w]
            current = 0
        else:
            return None
        seen = True
    return total + current if seen else None


def _sum_findings(fields: dict) -> list[dict]:
    out: list[dict] = []
    amount, fee, total = money(fields.get("amount_text")), money(fields.get("fee_text")), money(fields.get("total_text"))
    if amount is not None and total is not None:
        if abs(total - amount) > 0.5 and abs(total - (amount + (fee or 0))) > 0.5:
            out.append({"id": "total_mismatch", "severity": "high", "text": _t(
                f"The numbers do not add up: amount {fields.get('amount_text')} + fee {fields.get('fee_text') or '0'} "
                f"is not the total {fields.get('total_text')}. Edited receipts often change one number and forget the other.",
                f"حساب نہیں ملتا: رقم {fields.get('amount_text')} + فیس {fields.get('fee_text') or '0'} کل رقم "
                f"{fields.get('total_text')} کے برابر نہیں۔ ایڈٹ شدہ رسید میں اکثر ایک رقم بدلی جاتی ہے، دوسری بھول جاتے ہیں۔",
                f"Hisaab nahi milta: raqam {fields.get('amount_text')} + fee {fields.get('fee_text') or '0'} total "
                f"{fields.get('total_text')} ke barabar nahi. Edit ki gayi raseed mein aksar ek raqam badli jati hai, doosri bhool jate hain.")})
    in_words = words_to_number(fields.get("amount_in_words"))
    if amount is not None and in_words is not None and abs(in_words - int(amount)) >= 1:
        out.append({"id": "words_mismatch", "severity": "high", "text": _t(
            f"The amount in figures ({fields.get('amount_text')}) and in words (\"{fields.get('amount_in_words')}\" = {in_words:,}) differ.",
            f"ہندسوں میں رقم ({fields.get('amount_text')}) اور الفاظ میں رقم ({in_words:,}) مختلف ہیں۔",
            f"Digits mein raqam ({fields.get('amount_text')}) aur alfaz mein raqam ({in_words:,}) mukhtalif hain.")})
    return out


# --------------------------------------------------------------------------- IBAN, brand name

_IBAN = re.compile(r"PK\d{2}[A-Z]{4}[\dA-Z*xX•]{8,20}", re.I)


def iban_valid(iban: str) -> bool:
    v = iban.upper()
    moved = v[4:] + v[:4]
    digits = "".join(str(int(ch, 36)) for ch in moved)
    return int(digits) % 97 == 1


def _iban_findings(fields: dict) -> list[dict]:
    out: list[dict] = []
    for key in ("sender_account_masked", "receiver_account_masked"):
        raw = re.sub(r"[\s-]", "", str(fields.get(key) or ""))
        m = _IBAN.search(raw)
        if not m:
            continue
        iban = m.group(0)
        if len(iban) != 24:
            out.append({"id": "iban_length", "severity": "medium", "text": _t(
                f"The IBAN \"{iban}\" has {len(iban)} characters; Pakistani IBANs have 24.",
                f"آئی بین \"{iban}\" میں {len(iban)} حروف ہیں؛ پاکستانی آئی بین 24 حروف کا ہوتا ہے۔",
                f"IBAN \"{iban}\" mein {len(iban)} characters hain; Pakistani IBAN 24 characters ka hota hai.")})
        elif iban[4:].isalnum() and not re.search(r"[*xX•]", iban[8:]) and not iban_valid(iban):
            out.append({"id": "iban_checksum", "severity": "high", "text": _t(
                f"The IBAN \"{iban}\" fails the IBAN check digits, so it was typed or edited by hand.",
                f"آئی بین \"{iban}\" کے چیک ہندسے درست نہیں، یعنی یہ ہاتھ سے لکھا یا بدلا گیا ہے۔",
                f"IBAN \"{iban}\" ke check digits durust nahi, yani yeh haath se likha ya badla gaya hai.")})
    return out


KNOWN_BRANDS = ("jazzcash", "easypaisa", "sadapay", "nayapay", "upaisa", "meezanbank", "habibbank", "unitedbank",
                "alliedbank", "bankalfalah", "bankalhabib", "faysalbank", "askaribank", "bankislami", "standardchartered",
                "nationalbank", "soneribank", "dubaiislamic", "jsbank", "raast")


def _distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _brand_findings(fields: dict) -> list[dict]:
    name = str(fields.get("app_name") or "")
    words = re.findall(r"[a-z]+", name.lower())
    joined = "".join(words)
    if not joined or any(b in joined for b in KNOWN_BRANDS):
        return []
    for size in (2, 1, 3):
        for i in range(len(words) - size + 1):
            chunk = "".join(words[i:i + size])
            for brand in KNOWN_BRANDS:
                if len(brand) >= 6 and 0 < _distance(chunk, brand) <= (1 if len(brand) < 8 else 2):
                    return [{"id": "brand_spelling", "severity": "high", "text": _t(
                        f"The name on the receipt is \"{name}\", a misspelling of a real app or bank. Real receipts spell their own name right.",
                        f"رسید پر نام \"{name}\" لکھا ہے جو اصل ایپ یا بینک کے نام کا غلط ہجہ ہے۔ اصلی رسید پر اپنا نام صحیح لکھا ہوتا ہے۔",
                        f"Raseed par naam \"{name}\" likha hai jo asli app ya bank ke naam ki ghalat spelling hai. Asli raseed par apna naam sahi likha hota hai.")}]
    return []


# --------------------------------------------------------------------------- what the person expected

def _same_account(shown: str, mine: str) -> bool | None:
    """Compare from the right, skipping hidden characters. None when there is too little to compare."""
    def norm(v: str) -> str:
        v = re.sub(r"[\s-]", "", v).upper()
        return re.sub(r"^(?:\+92|0092|92)(?=3)", "0", v)

    a, b = norm(shown), norm(mine)
    a_mobile, b_mobile = bool(re.match(r"03", a)), bool(re.match(r"03", b))
    b_short = b.isdigit() and len(b) <= 6
    if not b_short and (a_mobile != b_mobile or a.startswith("PK") != b.startswith("PK")):
        return None
    compared = 0
    for x, y in zip(reversed(a), reversed(b), strict=False):
        if x in _MASK_CHARS or y in _MASK_CHARS or not (x.isalnum() and y.isalnum()):
            continue
        if x != y:
            return False
        compared += 1
    return True if compared >= 3 else None


def _expectation_findings(fields: dict, expected_amount: str | None, my_account: str | None) -> list[dict]:
    out: list[dict] = []
    amount, expected = money(fields.get("amount_text")), money(expected_amount)
    if expected is not None and re.search(r"\d\s*k\b", expected_amount or "", re.I):
        expected *= 1000  # "2.5k"
    elif expected is not None and re.search(r"\d\s*(lakh|lac)\b", expected_amount or "", re.I):
        expected *= 100_000
    if amount is not None and expected:
        if amount > expected + 0.5:
            out.append({"id": "overpaid", "severity": "high", "text": _t(
                f"The receipt shows {fields.get('amount_text')}, more than the {expected:,.0f} you expected. \"I sent too much, "
                "please return the difference\" is a common trick: the extra money never arrived.",
                f"رسید پر {fields.get('amount_text')} ہیں، آپ کی متوقع رقم {expected:,.0f} سے زیادہ۔ \"زیادہ بھیج دیے، فرق واپس کریں\" "
                "ایک عام چال ہے: زیادہ رقم کبھی آئی ہی نہیں ہوتی۔",
                f"Raseed par {fields.get('amount_text')} hain, aap ki tawaqqo {expected:,.0f} se zyada. \"Zyada bhej diye, farq wapas "
                "karein\" aam chaal hai: zyada raqam kabhi aayi hi nahi hoti.")})
        elif amount < expected - 0.5:
            out.append({"id": "underpaid", "severity": "medium", "text": _t(
                f"The receipt shows {fields.get('amount_text')}, less than the {expected:,.0f} you expected.",
                f"رسید پر {fields.get('amount_text')} ہیں، آپ کی متوقع رقم {expected:,.0f} سے کم۔",
                f"Raseed par {fields.get('amount_text')} hain, aap ki tawaqqo {expected:,.0f} se kam.")})
    receiver = fields.get("receiver_account_masked")
    if my_account and receiver and _same_account(str(receiver), my_account) is False:
        out.append({"id": "not_your_account", "severity": "high", "text": _t(
            f"The money went to {receiver}, not to your number or account. Either the receipt is fake or it is someone else's payment.",
            f"رقم {receiver} کو گئی ہے، آپ کے نمبر یا اکاؤنٹ میں نہیں۔ یا تو رسید جعلی ہے یا یہ کسی اور کی ادائیگی ہے۔",
            f"Raqam {receiver} ko gayi hai, aap ke number ya account mein nahi. Ya to raseed jaali hai ya yeh kisi aur ki payment hai.")})
    return out


# --------------------------------------------------------------------------- the image file

def image_findings(meta: dict) -> list[dict]:
    out: list[dict] = []
    if meta.get("ai"):
        names = ", ".join(meta["ai"])
        out.append({"id": "ai_generated", "severity": "high", "text": _t(
            f"The image file says it was made by {names}. A real receipt comes from the payment app, not an AI image tool.",
            f"تصویر کی فائل کے مطابق یہ {names} سے بنی ہے۔ اصلی رسید ادائیگی کی ایپ سے آتی ہے، اے آئی تصویر بنانے والے ٹول سے نہیں۔",
            f"Tasveer ki file ke mutabiq yeh {names} se bani hai. Asli raseed payment app se aati hai, AI image tool se nahi.")})
    if meta.get("editors"):
        names = ", ".join(meta["editors"])
        out.append({"id": "edited_image", "severity": "medium", "text": _t(
            f"The image was saved by an editing app ({names}). A receipt shared straight from the payment app is not edited.",
            f"تصویر ایڈیٹنگ ایپ ({names}) سے محفوظ کی گئی ہے۔ ادائیگی کی ایپ سے سیدھی بھیجی گئی رسید ایڈٹ نہیں ہوتی۔",
            f"Tasveer editing app ({names}) se save ki gayi hai. Payment app se seedhi bheji gayi raseed edit nahi hoti.")})
    size = (meta.get("width"), meta.get("height"))
    if size in AI_SIZES and not meta.get("ai"):
        out.append({"id": "ai_size", "severity": "medium", "text": _t(
            f"The image is exactly {size[0]}x{size[1]} pixels, a size AI image generators produce. Phone screenshots "
            "have the phone's screen size (for example 1080x2400).",
            f"تصویر بالکل {size[0]}x{size[1]} پکسل کی ہے، جو اے آئی تصویر بنانے والے ٹولز کا سائز ہے۔ فون کا اسکرین شاٹ "
            "فون کی اسکرین کے سائز کا ہوتا ہے (جیسے 1080x2400)۔",
            f"Tasveer bilkul {size[0]}x{size[1]} pixel ki hai, jo AI image tools ka size hai. Phone ka screenshot phone ki "
            "screen ke size ka hota hai (jaise 1080x2400).")})
    return out


async def _read_fields(settings: Settings, data: bytes, mime: str) -> dict:
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
    return normalize_fields(raw if isinstance(raw, dict) else {})


async def number_findings(deps, fields: dict) -> list[dict]:
    """Fully visible numbers on the receipt that reviewers confirmed as scam numbers."""
    from app.intel.lookup import lookup

    out: list[dict] = []
    for key in ("receiver_account_masked", "sender_account_masked"):
        value = re.sub(r"[\s-]", "", str(fields.get(key) or ""))
        if not value or re.search(rf"[{re.escape(_MASK_CHARS)}]", value):
            continue
        if re.fullmatch(r"(?:\+92|0092|92|0)3\d{9}", value):
            kind = "phone"
        elif re.fullmatch(r"PK\d{2}[A-Z]{4}\d{16}", value, re.I):
            kind = "account"
        else:
            continue
        try:
            result = await lookup(deps, value, kind)
        except Exception:
            continue
        if result.get("status") in ("known_scam", "reported"):
            out.append({"id": "reported_number", "severity": "high", "text": _t(
                f"{value} on this receipt is a number or account reviewers have confirmed in scam reports.",
                f"اس رسید پر موجود {value} وہ نمبر یا اکاؤنٹ ہے جو تصدیق شدہ فراڈ رپورٹس میں ہے۔",
                f"Is raseed par mojood {value} woh number ya account hai jo tasdeeq shuda fraud reports mein hai.")})
    return out


async def history_findings(deps, fields: dict, user: str | None, flagged: bool) -> list[dict]:
    """The same receipt (transaction ID and amount) checked before by someone else, or found fake before.

    Fake receipts are sent to many sellers. Only a keyed hash is stored, so nobody can read the
    transaction ID back. Someone who knows a real receipt's ID and amount could make it look
    'seen before'; the result is only a warning to check the app, which is the advice anyway.
    """
    from app.core.redaction import fingerprint
    from app.db.models import ReceiptSeen

    labels = {"TID", "TRX", "TXN", "TRANSACTION", "TRANS", "ID", "REF", "REFERENCE", "NO", "NUMBER", "RRN", "STAN"}
    tokens = re.findall(r"[0-9A-Za-z]+", str(fields.get("transaction_id") or "").upper())
    tid = "".join(t for t in tokens if t not in labels)
    if len(tid) < 6:
        return []
    amount = money(fields.get("amount_text"))
    key = fingerprint(f"receipt:{tid}:{amount if amount is not None else ''}", deps.settings.fingerprint_secret)
    now = datetime.now(UTC)
    out: list[dict] = []
    async with deps.sessionmaker() as session:
        row = await session.get(ReceiptSeen, key)
        if row is None:
            session.add(ReceiptSeen(fingerprint=key, first_seen=now, last_seen=now, first_user=user, checks=1,
                                    other_users=0, flagged=flagged))
        else:
            other = user is None or row.first_user is None or row.first_user != user
            day = row.first_seen.strftime("%d %b %Y")
            if other and row.flagged:
                out.append({"id": "seen_fake", "severity": "high", "text": _t(
                    f"This same receipt (same transaction ID and amount) was already checked on {day} and showed signs of being fake.",
                    f"یہی رسید (وہی ٹرانزیکشن آئی ڈی اور رقم) {day} کو بھی چیک ہوئی تھی اور اس میں جعلی ہونے کی نشانیاں تھیں۔",
                    f"Yehi raseed (wohi transaction ID aur raqam) {day} ko bhi check hui thi aur us mein jaali hone ki nishaniyan thin.")})
            elif other:
                out.append({"id": "seen_before", "severity": "medium", "text": _t(
                    f"Someone else checked this same receipt (same transaction ID and amount) on {day}. Scammers send one "
                    "receipt to many sellers; make sure the money is in your own app.",
                    f"کسی اور نے یہی رسید (وہی ٹرانزیکشن آئی ڈی اور رقم) {day} کو چیک کی تھی۔ فراڈیے ایک رسید کئی "
                    "دکانداروں کو بھیجتے ہیں؛ اپنی ایپ میں رقم ضرور دیکھیں۔",
                    f"Kisi aur ne yehi raseed (wohi transaction ID aur raqam) {day} ko check ki thi. Fraudiye ek raseed kai "
                    "dukandaron ko bhejte hain; apni app mein raqam zaroor dekhein.")})
            row.checks += 1
            row.last_seen = now
            row.other_users += int(other)
            row.flagged = row.flagged or flagged
        await session.commit()
    return out


async def read_receipt(deps, data: bytes, mime: str, expected_amount: str | None = None,
                       my_account: str | None = None, user: str | None = None) -> dict:
    settings = deps.settings
    meta = inspect(data)
    fields: dict = {}
    unavailable = None
    if not settings.google_api_key:
        unavailable = ("Reading the text of payment screenshots needs GOOGLE_API_KEY (Gemini). "
                       "The checks on the image file still ran.")
    else:
        try:
            fields = await _read_fields(settings, data, mime)
        except Exception:
            unavailable = "The text of the screenshot could not be read right now. The checks on the image file still ran."
    findings = image_findings(meta)
    if fields:
        findings = consistency_findings(fields, expected_amount=expected_amount, my_account=my_account) + findings
        findings += await number_findings(deps, fields)
        findings += await history_findings(deps, fields, user, assessment(findings) == "likely_fake")
    out = {"experimental": True, "fields": fields, "findings": findings, "assessment": assessment(findings),
           "advice": ADVICE, "image": {"width": meta.get("width"), "height": meta.get("height")},
           "model": settings.gemini_vision_model if fields else None}
    if unavailable:
        out["unavailable"] = unavailable
    return out

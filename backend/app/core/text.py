"""Text normalisation and language detection.

Replies are written in English, Urdu script or Roman Urdu. Pashto, Sindhi and Punjabi
(Shahmukhi or Roman) are recognised so the result can say so; the pattern rules cover a
few common words in them and the AI reading covers the rest.
"""

import re
import unicodedata
from typing import Literal

Language = Literal["en", "ur", "roman"]

_URDU_DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭ]")
_ZERO_WIDTH = re.compile(r"[​-‏‪-‮⁦-⁩﻿]")
_REPEATS = re.compile(r"([a-z])\1{2,}")
_SPACES = re.compile(r"\s+")
_URDU_CHARS = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN_CHARS = re.compile(r"[A-Za-z]")

# Arabic code points that Urdu keyboards and copy-paste mix with Urdu ones.
URDU_CHAR_MAP = _CHAR_MAP = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ه": "ہ",
        "ة": "ہ",
        "ۃ": "ہ",
        "أ": "ا",
        "إ": "ا",
        "آ": "آ",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        # Pashto and Sindhi forms of shared letters, so Urdu patterns still match.
        "ڪ": "ک",
        "ګ": "گ",
        "ې": "ی",
        "ۍ": "ی",
    }
)

# Cyrillic and Greek letters that look like Latin ones. Scammers mix them in ("НВL", "раssword")
# to slip past filters, so matching works on the folded form and the mix itself is a signal.
CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
        "ѕ": "s", "һ": "h", "ԁ": "d", "ӏ": "l", "ԛ": "q", "ԝ": "w",
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
        "Т": "T", "Х": "X", "У": "Y", "І": "I", "Ј": "J", "Ѕ": "S",
        "α": "a", "ο": "o", "ρ": "p", "ν": "v", "τ": "t", "ι": "i", "κ": "k",
        "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N",
        "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    }
)
_CYRILLIC_GREEK = re.compile(r"[Ͱ-ϿЀ-ӿԀ-ԯ]")
_MIXED_WORD = re.compile(r"[^\W\d_]+")
# "O T P", "p.i.n", "c-o-d-e": letters spaced out to dodge keyword filters.
_SPACED_LETTERS = re.compile(r"(?<![a-z])(?:[a-z][ .\-_*]){2,}[a-z](?![a-z])")

# Common Roman Urdu function words. Several hits in a Latin-script message mean Roman Urdu.
_ROMAN_URDU_WORDS = {
    "hai", "hain", "ho", "hoon", "hun", "aap", "ap", "apka", "apki", "aapka", "aapki", "ka",
    "ki", "ke", "ko", "mein", "main", "mai", "me", "kar", "karein", "karen", "karain", "kren",
    "nahi", "nai", "nahin", "bhej", "bhejein", "bhejen", "bhejo", "jaldi", "abhi", "kya", "kyun",
    "kaise", "yeh", "ye", "woh", "wo", "raha", "rahi", "gaya", "gayi", "diya", "dein", "do",
    "paise", "paisay", "rupay", "mubarak", "inaam", "lekin", "aur", "bhi", "sirf", "wala",
    "wali", "hum", "tum", "mera", "meri", "apna", "apni", "batao", "bataein", "batayen",
}


def fold_confusables(text: str) -> str:
    return text.translate(CONFUSABLES)


def mixed_script_words(text: str) -> list[str]:
    """Words that mix Latin letters with look-alike Cyrillic or Greek ones."""
    out = []
    for word in _MIXED_WORD.findall(unicodedata.normalize("NFKC", _ZERO_WIDTH.sub("", text))):
        if _CYRILLIC_GREEK.search(word) and re.search(r"[A-Za-z]", word):
            out.append(word)
    return out[:5]


def normalize(text: str) -> str:
    """Lower-case, strip diacritics and invisible characters, unify Urdu letters, fold look-alikes."""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    text = text.translate(_CHAR_MAP).translate(CONFUSABLES)
    text = _URDU_DIACRITICS.sub("", text)
    text = text.lower()
    text = _SPACED_LETTERS.sub(lambda m: re.sub(r"[ .\-_*]", "", m.group(0)), text)
    text = _REPEATS.sub(r"\1", text)
    return _SPACES.sub(" ", text).strip()


def detect_language(text: str) -> Language:
    """Guess whether a message is in Urdu script, Roman Urdu or English."""
    urdu = len(_URDU_CHARS.findall(text))
    latin = len(_LATIN_CHARS.findall(text))
    if urdu and urdu >= 0.3 * (urdu + latin):
        return "ur"
    words = re.findall(r"[a-z]+", normalize(text))
    if not words:
        return "en"
    hits = sum(1 for w in words if w in _ROMAN_URDU_WORDS)
    if hits >= 2 and hits / len(words) >= 0.08:
        return "roman"
    return "en"


_PASHTO_LETTERS = re.compile(r"[ټډړږښځڅګۍې]")
_SINDHI_LETTERS = re.compile(r"[ٻڄڃڇڊڌڍڎڏڙڦڪڳڱڻ]")
_PUNJABI_WORDS = {
    "تسیں", "تسی", "تہاڈا", "تہاڈی", "تہاڈے", "تہانوں", "ساڈا", "ساڈی", "ساڈے", "سانوں", "مینوں",
    "تینوں", "کتھے", "وچ", "نال", "ہیگا", "کیہ",
}
_ROMAN_PUNJABI_WORDS = {
    "tusi", "tussi", "tuhada", "tuhadi", "tuhade", "tuhanu", "sanu", "saanu", "sada", "saada", "mainu",
    "tenu", "kithe", "vich", "nal", "naal", "hega", "haige", "kiddan", "kidda", "karo ji",
}
SOURCE_LANGUAGE_NAMES = {
    "en": "English", "ur": "Urdu", "roman": "Roman Urdu", "ps": "Pashto", "sd": "Sindhi",
    "pa": "Punjabi (Shahmukhi)", "pa_roman": "Punjabi (Roman)",
}


def detect_source_language(text: str) -> str:
    """The language the message is written in. Wider than the reply languages (en, ur, roman)."""
    t = unicodedata.normalize("NFKC", text)
    if len(_SINDHI_LETTERS.findall(t)) >= 2:
        return "sd"
    if len(_PASHTO_LETTERS.findall(t)) >= 2:
        return "ps"
    words = re.findall(r"[؀-ۿ]+", t)
    if sum(1 for w in words if w in _PUNJABI_WORDS) >= 2:
        return "pa"
    latin = re.findall(r"[a-z]+", t.lower())
    if sum(1 for w in latin if w in _ROMAN_PUNJABI_WORDS) >= 2:
        return "pa_roman"
    return detect_language(text)


def reply_language_for(source_language: str) -> Language:
    """Pashto, Sindhi and Shahmukhi Punjabi readers get Urdu script; Roman Punjabi gets Roman Urdu."""
    if source_language in ("ps", "sd", "pa"):
        return "ur"
    if source_language == "pa_roman":
        return "roman"
    return source_language if source_language in ("en", "ur", "roman") else "en"  # type: ignore[return-value]


def detect_language_request(text: str) -> Language | None:
    """Spot an explicit request to reply in a language, e.g. 'urdu mein batao'."""
    t = normalize(text)
    if re.search(r"\b(reply|answer|respond|talk|write)\s+in\s+english\b|\benglish (mein|me|main) (batao|bataein|likho|jawab)", t):
        return "en"
    if re.search(r"\broman urdu\b", t):
        return "roman"
    if re.search(r"\burdu (mein|me|main|men) (batao|bataein|batayen|likho|jawab|bolo)\b|\breply in urdu\b|\bin urdu\b|اردو میں", t):
        return "ur"
    return None


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?\n۔؟])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]

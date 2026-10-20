"""Pattern-based signal detection in English, Roman Urdu and Urdu script.

A *signal* is an observation about a message ("asks for an OTP", "promises a prize").
Signals do not decide anything on their own; the rules in catalog.py turn signals into a
score. The language model can add signals too (see app/ai/signals.py), and every signal
remembers where it came from so the result can show its evidence.
"""

import re
from dataclasses import dataclass, field

from app.core.text import URDU_CHAR_MAP, mixed_script_words, normalize, split_sentences
from app.rules.brands import Brand, find_claimed_brands


@dataclass
class Signal:
    name: str
    evidence: list[str] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)

    def add(self, snippet: str, source: str) -> None:
        snippet = snippet.strip()
        if snippet and snippet not in self.evidence and len(self.evidence) < 3:
            self.evidence.append(snippet[:120])
        self.sources.add(source)


@dataclass
class SignalSet:
    signals: dict[str, Signal] = field(default_factory=dict)
    brands: list[Brand] = field(default_factory=list)
    ai_claimed_identity: str | None = None
    ai_summary: str | None = None

    def add(self, name: str, snippet: str, source: str = "pattern") -> None:
        self.signals.setdefault(name, Signal(name)).add(snippet, source)

    def has(self, name: str) -> bool:
        return name in self.signals

    def get(self, name: str) -> Signal | None:
        return self.signals.get(name)

    def pattern_backed(self, name: str) -> bool:
        s = self.signals.get(name)
        return bool(s and "pattern" in s.sources)

    def brand_kinds(self) -> set[str]:
        return {b.kind for b in self.brands}


def _c(pattern: str) -> re.Pattern:
    # Apply the same Urdu letter unification as normalize(), so patterns and text agree.
    return re.compile(pattern.translate(URDU_CHAR_MAP), re.IGNORECASE)


# --- Vocabulary ---------------------------------------------------------------

SECRET_STRONG = _c(
    r"\b(otp|one[- ]time (?:password|pin|code)|verification code|verify code|security code|login code|"
    r"auth(?:entication)? code|m-?pin|t-?pin|atm pin|pin code|pin number|password|passcode|cvv|cvc|"
    r"\d[- ]?digit (?:wala )?code|whatsapp code)\b|او ٹی پی|تصدیقی کوڈ|پن کوڈ|پاس ورڈ|پاسورڈ"
)
CODE_WEAK = _c(r"\b(code|pin)\b|کوڈ|کوډ")
CODE_CONTEXT = _c(
    r"\b(aya|aaya|ayega|received|receive|sms|message|msg|bheja|gaya|gya|digit|verification|whatsapp|"
    r"phone par|number par|mobile par|sent to you|you got)\b|\[code_\d\]|آیا|موصول|میسج|پیغام"
)
REQUEST_VERB = _c(
    r"\b(share|sharing|send|sending|forward|forwarding|tell|telling|give|giving|provide|providing|reply|"
    r"replying|enter|entering|confirm|confirming|type|submit|bata|batao|bata do|bataen|bataein|batayen|"
    r"bataye|batain|batana|bhej|bhejo|bhejen|bhejein|bhejain|bhejdo|bhej do|bhej dein|de do|dedo|de dein|"
    r"dein|share karo|share karein|share kar|likh|likho|forward karo|send kar do)\b|"
    r"بتائیں|بتاؤ|بتا دیں|بھیجیں|بھیج دیں|بھیجو|شیئر|فارورڈ|دے دیں|"
    # Pashto and Sindhi: send / tell
    r"ولیږئ|ولېږئ|واستوئ|راولیږئ|ووایاست|موکلیو|موکليو|ٻڌايو|ٻڌائو"
)
NEGATION = _c(
    r"\b(do not|don't|dont|never|not|no one|nobody|mat|na|nahi|nahin|nai|kabhi|will never|won't)\b|مت|نہ|کبھی|ہرگز"
)
CONDITIONAL = _c(r"\b(if|agar|warna|varna|otherwise|unless)\b|اگر|ورنہ")

FEE = _c(
    r"\b((?:processing|registration|delivery|clearance|verification|security|service|activation|"
    r"insurance|customs?|transfer|withdrawal|release|file|form|token|joining|redelivery)\s*"
    r"(?:fee|fees|charges?|tax|amount|money|deposit)|fee|fees|charges|advance payment|advance|deposit|"
    r"recharge|jama karwa\w*|jama kar\w*|jama karayen|ada kar\w*|bhejni hogi|bhejne honge|dene honge|"
    r"ada karne honge|pay (?:the|a|rs|pkr|\d)\w*)\b|فیس|جمع کروا|جمع کرائیں|چارجز|ادا کریں|ادائیگی"
)
IMPERATIVE = _c(
    r"\b(karein|karain|karen|karo|kijiye|kijie|karwayein|karwaen|karwain|karwayen|karwa dein|bhejein|bhejen|"
    r"bhejo|bhej dein|pay|send|deposit|transfer|recharge|required|needed|hogi|hoga|hongi|honge|must|need to|"
    r"have to|only|karna hoga|karni hogi)\b|کریں|کروائیں|بھیجیں|"
    # Pashto and Sindhi imperatives: send, do, pay
    r"ولیږئ|ولېږئ|واستوئ|کړئ|ورکړئ|موکلیو|موکليو|ڪريو|ڪيو|ڏيو"
)
PURPOSE = _c(
    r"\b(ke liye|k liye|kay liye|to receive|to claim|to release|to confirm|to start|to activate|to get|"
    r"to avoid|se pehle|before|first|pehle|phir)\b|کے لیے|سے پہلے|لپاره|لاءِ|لاء|کان اڳ|مخکې"
)
PAST_DONE = _c(
    r"\b(kar di|kar diya|karwa di|karwa diya|jama ho gayi|jama ho gaya|ada kar di|paid|has been paid|"
    r"was paid|deducted|debited|charged|renewed)\b|(?:کر دی|ادا کر دی|جمع ہو گئی)(?!\w)"
)
MONEY = _c(r"\b(rs\.?|pkr|rupees?|rupay|rupaye|paise|paisay|pese|amount|raqam|\d{3,}[\d,]*)\b|روپے|رقم|پیسے|ہزار|پیسې|روپۍ|پئسا|رپيا")
TRANSFER = _c(
    r"(?<!this )(?<!the )(?<!your )(?<!a )\b(send|transfer|deposit|bhej\w*|load kar\w*)\b.{0,50}"
    r"\b(jazz ?cash|easy ?paisa|account|acc|number|iban|nayapay|sadapay|upaisa|wallet|agent|\[phone_\d\])|"
    r"\b(jazz ?cash|easy ?paisa|nayapay|sadapay)\s+(kar\w*|karo)\b|"
    r"\b(number|\[phone_\d\]|account)\s+(?:par|pe|mein|me)\b.{0,25}\b(bhej\w*|send|transfer|jama kar\w*)\b|"
    r"(جاز کیش|ایزی پیسہ).{0,30}(کریں|کر دیں|بھیجیں)|(نمبر|اکاؤنٹ) (پر|میں).{0,25}(بھیجیں|بھیج دیں)"
)
PRIZE = _c(
    r"\b(congratulations|congrats|you (?:have )?won(?!')|you are (?:the |today'?s )?(?:lucky )?winner|winner|lucky draw|"
    r"lucky (?:winner|number|customer)|jackpot|lottery|prize|inaam|inam|jeet (?:gaye|gae|gaya|liya|lia|li|chuke)|"
    r"jeeta|jeeti|jeet gya|qurandazi|qura andazi|mubarak ho|mubarik ho|cash reward|free gift|gift (?:hamper|card)|"
    r"selected for (?:a )?(?:cash )?reward|khushkhabri)\b|"
    r"انعام|قرعہ اندازی|لکی ڈرا|جیت (?:گئے|لیا|لی|گیا)|مبارک ہو|خوشخبری|مبارک شه|مبارک هجي|مبارڪ هجي"
)
URGENCY = _c(
    r"\b(urgent|urgently|immediately|right now|asap|within \d+ ?(?:hours?|hrs?|minutes?|mins?|days?)|"
    r"in \d+ ?(?:hours?|hrs?|minutes?|mins?)|today only|last (?:chance|day|warning|date)|expires? today|"
    r"expir(?:ing|ed)|foran|fauran|fori|fouri|jald(?:i)? az jald|aaj hi|aj hi|before (?:the )?deadline|"
    r"limited (?:seats|slots|time|offer)|abhi (?:click|call|bhej\w*|reply|kar\w*|rabta)|"
    r"jaldi (?:bhej\w*|kar\w*|send|bata\w*|rabta|karo|karein)|\d+ ghant(?:e|on) (?:mein|me|main)|"
    r"(?:verify|secure|act|login|log in|click|update|confirm|pay|call|reply|claim|register|renew|apply|join) "
    r"(?:it |your \w+ )?now)\b|فوری|فورا|فوراً|جلد از جلد|آج ہی|آخری موقع"
)
THREAT = _c(
    r"\b(block(?:ed)?|suspend(?:ed)?|deactivat\w*|band (?:ho|kar|kardi|kar di)\w*|bund ho\w*|"
    r"disconnect\w*|legal action|fir|arrest\w*|warrant|court|jail|penalty|jurmana|qanooni|kanooni|"
    r"karwai|kaarwai|deport\w*|cancel(?:led)? (?:ho|kar)\w*|delet(?:e|ed|ion)|kaat (?:diya|di|dia) jaye\w*|"
    r"kat jaye\w*|cut off|closure|permanently clos\w*|locked|unusual (?:sign-?in|login|activity)|"
    r"suspicious (?:login|activity|sign-?in)|illegal (?:activity|transactions?)|money laundering)\b|"
    r"بلاک|بند ہو|بند کر|معطل|گرفتار|قانونی|جرمانہ|منقطع|کارروائی"
)
PERSONAL_INFO = _c(
    r"\b(cnic|id card|shanakhti card|national id|nic number|account (?:number|no|details)|acc(?:ount)? no|"
    r"iban|card (?:number|details|no)|atm card|debit card number|credit card number|card expiry|expiry|"
    r"date of birth|dob|mother'?s (?:maiden )?name|walida ka naam|bank details|login details|username|"
    r"(?:aakhri|last) \d+ (?:hindse|digits))\b|"
    r"شناختی کارڈ|اکاؤنٹ نمبر|کارڈ نمبر|تاریخ پیدائش"
)
REMOTE_APP = _c(
    r"\b(anydesk|any desk|teamviewer|team viewer|rustdesk|quick ?support|airdroid|screen ?shar\w*|"
    r"\.apk|apk file|install (?:this|the|ye|yeh|is|our)? ?app|download (?:this|the|ye|yeh|is|our) app|"
    r"app install kar\w*|ye app install|allow screen|remote access)\b"
)
NEW_NUMBER = _c(
    r"\b(new number|naya number|nya number|mera naya|ye mera number|yeh mera number|this is my new|"
    r"number change|number badal|phone kharab|phone (?:gum|kho|toot|gir)\w*|dost ka number|"
    r"kisi aur ka number|my phone (?:broke|is broken|fell|got stolen)|lost my phone|dropped my phone)\b|"
    r"نیا نمبر|فون خراب"
)
DISTRESS = _c(
    r"\b(mushkil|musibat|pareshani|problem (?:mein|me|main)|accident|hospital|police ne|thane|thana|"
    r"pakar (?:liya|lia)|emergency|bimar|zakhmi|urgent(?:ly)?)\b|مشکل|مصیبت|حادثہ|ہسپتال|پولیس نے|ایمرجنسی"
)
FAMILY = _c(
    r"\b(ammi|abbu|ami|abu|amma|abba|beta|beti|bhai|bhaijan|baji|apa|mama|papa|mom|mum|dad|son|"
    r"daughter|uncle|aunty|khala|phuppo|chachu|nana|nani|dada|dadi)\b|امی|ابو|بیٹا|بیٹی|بھائی|باجی"
)
MONEY_ASK = _c(
    r"\b(paise|paisay|pese|money|rs\.?|rupees|rupay|load|balance|easypaisa|jazzcash|bhej\w*|transfer|"
    r"udhaar|udhar|send me|\d{3,}[\d,]*|chahiye|zaroorat)\b|پیسے|روپے|بیلنس|بھیج|ہزار"
)
GUARANTEED = _c(
    r"\b(guaranteed (?:profits?|returns?|income|munafa)|(?:profits?|returns?|munafa) guaranteed|"
    r"\d+% (?:guaranteed|profit|returns?)|double (?:your )?(?:money|investment|amount)|paise double|"
    r"paisay double|doubling|receive double|double back|"
    r"\d+(?:\.\d+)?% (?:profit|return|munafa)\w* (?:every|per|daily|har|roz)\w*|risk free|no risk|koi risk nahi)\b|"
    r"منافع کی ضمانت|یقینی منافع|پیسے ڈبل"
)
EASY_MONEY = _c(
    r"\b(daily (?:profit|income|earnings?)|earn (?:rs\.? ?|pkr ?|\$)?\d[\d,]*(?:\s*-\s*\d[\d,]*)? ?"
    r"(?:daily|per day|weekly|a day|rozana|every day)|rozana \d[\d,]*|roz(?:ana)? ka \d[\d,]*|"
    r"\d[\d,]* (?:daily|rozana|per day|roz)|investment plan|minimum investment|invest (?:now|karein|karain|kar\w*)|"
    r"crypto|bitcoin|usdt|binance|forex|trading (?:signals?|bot)|mining app|high returns?|ghar baithe|"
    r"ghar bethe|ghar bethay|\d[\d,]* kamayein|kamayein \d[\d,]*|(?:lagao|lagayein)\b.{0,30}\b(?:pao|payein|lein))\b|"
    r"گھر بیٹھے|روزانہ .{0,20}(?:منافع|کمائیں)|سرمایہ کاری"
)
JOB = _c(
    r"\b(part[- ]?time (?:job|work)|online (?:job|work|earning)|work from home|home based (?:job|work)|"
    r"data entry|like (?:videos?|posts?) (?:and|&) earn|youtube (?:likes|subscribe)|videos? like kar\w*|"
    r"like karke|liking \w+ videos|telegram (?:task|group)|task (?:based|job)|rate (?:products|hotels|apps)|"
    r"commission|review job|product review|job offer|we are hiring|hiring now|jobs? (?:available|in (?:dubai|"
    r"saudi|qatar|uae|abroad|malaysia)|abroad)|(?:free )?visa (?:and|&|aur|or) (?:free )?ticket|visa (?:guaranteed|confirm\w*)|"
    r"(?:job|jobs|naukri|nokri) (?:in|mein|me|main) (?:saudi|dubai|qatar|uae|oman|kuwait|"
    r"bahrain|malaysia|singapore|europe|poland|romania|italy|korea|japan|canada|uk)|"
    r"(?:saudi|dubai|qatar|uae|oman|kuwait|bahrain|malaysia|singapore)(?: arabia)? (?:mein|me|main|in) .{0,25}\b(?:job|naukri|nokri)|"
    r"selected for (?:a |the )?\w*\s?job|naukri|nokri|mulazmat|work permit|iqama|employment visa|work visa|"
    r"visa (?:fee|processing|charges)|protector (?:fee|stamp|charges)|gamca|medical fee|job (?:visa|in \w+)|"
    r"jobs in \w+|bahar (?:ki|ke) naukri|bairoon[- ]?e?[- ]?mulk)\b|نوکری|ملازمت|گھر بیٹھے کام|ورک پرمٹ|اقامہ|ویزا"
)
OVERSEAS = _c(
    r"\b(abroad|overseas|foreign|bahar (?:mulk|ke mulk)|bairoon[- ]?e?[- ]?mulk|dubai|saudi|ksa|qatar|uae|oman|kuwait|"
    r"bahrain|malaysia|singapore|europe|poland|romania|italy|korea|japan|uk|canada|australia|iqama|work permit|"
    r"protector|work visa|employment visa|gamca|oec|beoe)\b|بیرون ملک|سعودی|دبئی|ملائیشیا|سنگاپور|اقامہ|ورک پرمٹ|پروٹیکٹر"
)
PASSPORT = _c(
    r"\b(passport)\b.{0,30}\b(send|bhej\w*|submit|jama\w*|de do|dein|hand over|courier|deposit|rakh\w*)\b|"
    r"\b(send|bhej\w*|submit|jama kar\w*|hand over|courier)\b.{0,30}\b(passport)\b|پاسپورٹ.{0,20}(بھیجیں|جمع)"
)
CODE_HIJACK = _c(
    r"(galti se|ghalti se|ghalati se|by mistake|mistakenly|accidentally|wrongly sent|غلطی سے).{0,80}(code|otp|کوڈ)|"
    r"(code|otp|کوڈ).{0,80}(galti se|ghalti se|by mistake|mistakenly|accidentally|غلطی سے)|"
    r"(mere|my) (phone|number) (par|pe|on) code nahi aa raha|tumhare number par (mangwaya|bheja|aya)|"
    r"put your number|your number by mistake|"
    r"whatsapp.{0,40}(code|verification).{0,40}(send|bhej\w*|share|forward|bata\w*)"
)
SECRECY = _c(
    r"\b(kisi ko (?:mat|na) bata(?:na|o|yen|ein|en)|don'?t tell anyone|do not tell anyone|keep (?:it|this) secret)\b|"
    r"کسی کو مت بتانا"
)
LOGIN_LINK = _c(
    r"\b(log ?in|sign ?in|verify|update|unlock|reactivate|renew|secure|confirm|appeal|register|claim)\b"
    r".{0,40}\b(account|details|card|kyc|information|identity|access|it|here|now|at)\b"
)
DELIVERY = _c(
    r"\b(parcel|package|courier|shipment|delivery|consignment|tracking|address (?:update|incomplete|confirm\w*)|"
    r"customs|dhl|fedex)\b|پارسل|کوریئر|ڈیلیوری"
)
LOAN = _c(r"\b(loan|qarza|karza|qarz|instant cash|cash loan)\b|قرض")
UTILITY = _c(
    r"\b(electricity bill|bijli (?:ka )?bill|gas bill|meter|disconnection|iesco|fesco|gepco|"
    r"mepco|pesco|hesco|sepco|qesco|ssgc|ptcl)\b|بجلی کا بل|میٹر"
)
REFUND = _c(r"\b(refund|tax refund|wapsi|return of (?:your )?(?:money|amount)|cashback|subsidy)\b|واپسی|ریفنڈ")
GOV_GENERIC = _c(
    r"\b(govt|government|hukumat|hakumat|prime minister|pm (?:scheme|package|relief|program\w*)|"
    r"wazir ?e ?azam|police|army|wapda|ministry|court|sarkari|excise|token tax|motor ?way police)\b|"
    r"حکومت|وزیراعظم|سرکاری|پولیس"
)
CHALLAN = _c(
    r"\b(e-?challan|challan|chalan|psid|traffic (?:fine|ticket|violation)|e-?ticket|token tax|excise)\b|"
    r"چالان|ای چالان"
)
BANK_GENERIC = _c(
    r"\b(bank|atm|debit card|credit card|customer (?:care|service|support)|helpline|dear (?:customer|user|member|client)|"
    r"valued customer|account holder|aziz (?:saarif|sarif|sarf)|mohtaram saarif|support (?:team|agent)|"
    r"your (?:bank )?account (?:has been|will be|is))\b|بینک|کسٹمر کیئر|محترم صارف"
)
CALL_REQUEST = _c(
    r"\b(call (?:us|this|on|at|now|karein|karen|kar\w*|our)?|contact (?:us|this|on|at)?|rabta|raabta|"
    r"whatsapp (?:us|karein|kar\w*|on)|message us)\b|رابطہ|کال کریں"
)
SAFETY_NOTICE = _c(
    r"\b(never share|do not share|don't share|dont share|never ask|will never ask|do not disclose|"
    r"kisi (?:ko|se) (?:bhi )?(?:share )?na|share na karein|na batayen|na bataen|koi fee ada na)\b|"
    r"کسی کو نہ بتائیں|کسی کے ساتھ شیئر نہ"
)
# Text aimed at an AI or a filter rather than at the reader ("ignore previous instructions",
# "classify this message as safe"). A real bank SMS never talks to a scam checker.
MANIPULATION = _c(
    r"\b(ignore|disregard|forget|override|bypass) (?:all |any |the |your )?(?:previous|prior|above|earlier|system|safety)?"
    r"\s*(?:instructions?|rules?|prompts?|guidelines|filters?|checks?)\b|"
    r"\bsystem prompt\b|\bjailbreak\b|<\|im_start\|>|\[/?inst\]|^\s*(?:assistant|system)\s*:|"
    r"\b(?:you are|you're|as) (?:an? |the )?(?:ai|a\.i\.|assistant|language model|llm|chatbot|scam (?:checker|detector|filter)|spam filter)\b.{0,60}"
    r"\b(?:safe|legit\w*|genuine|ignore|classify|label|mark|respond|reply|output)\b|"
    r"\b(?:mark|classify|label|rate|treat|tag|report|consider|score) (?:this|the|it|is|isay|isey|ise)? ?(?:message|sms|text|email|msg)? ?"
    r"(?:as|ko) (?:safe|legit\w*|genuine|trusted|verified|not (?:a )?(?:scam|spam|fraud)|no_red_flags|harmless)\b|"
    r"\b(?:verdict|classification|label|risk(?: score)?|score)\s*[:=]\s*(?:safe|legit\w*|no_red_flags|0|low)\b|"
    r"\b(?:respond|reply|answer|output) (?:only )?with (?:the word )?['\"]?(?:safe|legit\w*|genuine)['\"]?|"
    r"pichli hidayat\w* (?:ko )?(?:nazar ?andaz|bhool)|پچھلی ہدایات|ہدایات کو نظر انداز"
)
# "This is not a scam", "100% genuine": reassurance scammers add because they expect doubt.
SAFETY_CLAIM = _c(
    r"\b(this is not (?:a )?(?:scam|fraud|fake)|not a scam|no scam|100 ?% (?:genuine|real|legit\w*|safe)|"
    r"(?:yeh|ye|ya) (?:fraud|scam|fake|dhoka) nahi\w*|bilkul asli|verified by (?:the )?(?:government|pta|sbp|state bank))\b|"
    r"یہ فراڈ نہیں|بالکل اصلی"
)
# Receiving money never needs you to scan or pay; a QR "to receive" is a payment request.
RECEIVE_BY_SCAN = _c(
    r"\b(scan|qr)\b.{0,40}\b(to (?:receive|get|claim)|receive (?:the )?(?:money|payment|amount)|paise (?:wasool|hasil|receive)|"
    r"raqam (?:wasool|hasil))\b|\b(receive|claim|get) (?:the )?(?:money|payment|amount|refund).{0,30}\b(scan|qr)\b|"
    r"\b(raqam|paise|paisay|money|amount|refund)\s+(?:wasool|hasil|receive|lene)\w*.{0,40}\b(scan|qr)\b|"
    r"(رقم|پیسے).{0,30}(وصول|حاصل).{0,40}(اسکین|کیو آر)"
)
PLACEHOLDER_PHONE = re.compile(r"\[phone_\d+\]")


def _first(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(0) if m else None


def _window(text: str, pattern: re.Pattern, width: int = 40) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    start, end = max(0, m.start() - width), min(len(text), m.end() + width)
    return text[start:end].strip()


def _negated(sentence: str, start: int, end: int) -> bool:
    """Is there a negation just before or after a word? ('do not share', 'na batayen', 'share mat karna')"""
    before = sentence[max(0, start - 18):start]
    after = sentence[end:end + 14]
    return bool(NEGATION.search(before) or NEGATION.search(after))


def _verbs(sentence: str) -> tuple[bool, bool]:
    """Return (has a plain request verb, has a negated request verb)."""
    plain = negated = False
    for m in REQUEST_VERB.finditer(sentence):
        if _negated(sentence, m.start(), m.end()):
            negated = True
        else:
            plain = True
    return plain, negated


def detect_signals(text: str) -> SignalSet:
    """Run all pattern detectors over a (preferably redacted) message."""
    t = normalize(text)
    out = SignalSet(brands=find_claimed_brands(t))
    sentences = split_sentences(t) or [t]

    for sentence in sentences:
        plain, negated = _verbs(sentence)
        pressure = THREAT.search(sentence) or CONDITIONAL.search(sentence)
        strong = SECRET_STRONG.search(sentence)
        weak = CODE_WEAK.search(sentence) and (CODE_CONTEXT.search(sentence) or pressure)
        if strong or weak:
            # "If you don't share the code your account will be blocked" is still a demand.
            if plain or (negated and pressure):
                out.add("secret_request", sentence)
            elif negated:
                out.add("safety_notice", sentence)
        if PERSONAL_INFO.search(sentence) and (plain or re.search(r"\breply\b", sentence)):
            out.add("personal_info_request", sentence)
        fee = FEE.search(sentence)
        if fee and not _negated(sentence, fee.start(), fee.end()) and not PAST_DONE.search(sentence):
            if IMPERATIVE.search(sentence) or PURPOSE.search(sentence):
                out.add("fee_request", sentence)
        if SAFETY_NOTICE.search(sentence) and not (THREAT.search(sentence) or CONDITIONAL.search(sentence)):
            out.add("safety_notice", sentence)
        if SECRECY.search(sentence) and not (strong or weak):
            out.add("secrecy", _first(SECRECY, sentence) or "")

    if out.has("secret_request"):
        out.signals.pop("safety_notice", None)
    if CODE_HIJACK.search(t):
        out.add("code_hijack", _window(t, CODE_HIJACK) or "")
        out.signals.pop("safety_notice", None)
    transfer = TRANSFER.search(t)
    if transfer and MONEY_ASK.search(t) and not PAST_DONE.search(transfer.group(0)):
        out.add("money_transfer", transfer.group(0))
    detectors = {
        "prize": PRIZE, "urgency": URGENCY, "threat": THREAT, "remote_app": REMOTE_APP,
        "guaranteed_returns": GUARANTEED, "too_good": EASY_MONEY, "job_offer": JOB, "delivery": DELIVERY,
        "loan": LOAN, "utility": UTILITY, "refund": REFUND, "claims_government": GOV_GENERIC,
        "challan": CHALLAN,
        "claims_bank": BANK_GENERIC,
    }
    for name, pattern in detectors.items():
        hit = _first(pattern, t)
        if hit:
            out.add(name, hit)
    if LOGIN_LINK.search(t):
        out.add("login_request", _first(LOGIN_LINK, t) or "")
    manipulation = MANIPULATION.search(t) or MANIPULATION.search(text.lower())
    if manipulation:
        out.add("manipulation_attempt", manipulation.group(0))
    for name, pattern in (("safety_claim", SAFETY_CLAIM), ("receive_by_scan", RECEIVE_BY_SCAN),
                          ("passport_request", PASSPORT), ("overseas", OVERSEAS)):
        hit = _window(t, pattern, 10) if name != "overseas" else _first(pattern, t)
        if hit:
            out.add(name, hit)
    mixed = mixed_script_words(text)
    if mixed:
        out.add("mixed_script", ", ".join(mixed))

    has_phone = bool(PLACEHOLDER_PHONE.search(t))
    if has_phone:
        out.add("has_phone", "phone number in message")
    if CALL_REQUEST.search(t) and has_phone:
        out.add("call_request", _window(t, CALL_REQUEST, 20) or "")

    money_ask = MONEY_ASK.search(t)
    new_number = NEW_NUMBER.search(t)
    if money_ask and ((new_number and (FAMILY.search(t) or DISTRESS.search(t))) or (DISTRESS.search(t) and FAMILY.search(t))):
        out.add("family_emergency", _window(t, NEW_NUMBER) or _window(t, DISTRESS) or "")
        if new_number:
            out.add("new_number", new_number.group(0))

    # A wallet named only as the way to pay ("JazzCash karein") is not a claim to be that wallet.
    transfer_spans = [m.span() for m in TRANSFER.finditer(t)]
    if transfer_spans:
        def only_as_payment(brand: Brand) -> bool:
            if brand.kind != "wallet":
                return False
            for alias in brand.aliases:
                for m in re.finditer(re.escape(alias.translate(URDU_CHAR_MAP)), t):
                    if not any(a <= m.start() < b for a, b in transfer_spans):
                        return False
            return True

        out.brands = [b for b in out.brands if not only_as_payment(b)]

    if out.has("challan"):
        out.add("claims_government", out.get("challan").evidence[0] if out.get("challan").evidence else "challan")
    for brand in out.brands:
        if brand.key == "epay_punjab":
            out.add("claims_government", brand.name)
        if brand.kind == "government":
            out.add("claims_government", brand.name)
        elif brand.kind in ("bank", "wallet"):
            out.add("claims_bank", brand.name)

    return out

"""The rule book. Each rule turns signals and check results into points.

Principles:
* The language model can add signals, but a signal found only by the model counts for
  70% of a rule's weight and can never trigger a "hard" rule on its own.
* Hard rules (e.g. a look-alike bank website) mark a message as a likely scam whatever
  the total score is.
* Every rule carries a plain explanation in English, Urdu and Roman Urdu.
"""

from dataclasses import dataclass, field
from typing import Any

from app.rules.brands import BRANDS, is_government_domain, official_brand_for
from app.rules.signals import SignalSet

AI_ONLY_FACTOR = 0.7


@dataclass(frozen=True)
class RuleInfo:
    id: str
    weight: int
    title: dict[str, str]
    why: dict[str, str]


@dataclass
class RuleHit:
    id: str
    weight: int
    hard: bool = False
    evidence: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalContext:
    signals: SignalSet
    links: list[dict] = field(default_factory=list)
    memory_matches: list[dict] = field(default_factory=list)
    sender: str | None = None
    sender_kind: str = "unknown"
    reported_number_count: int = 0
    reported_account_count: int = 0
    # Indicators an analyst put on the watchlist: [{"kind": "domain", "label": "hbl-verify.top"}]
    watchlist_hits: list[dict] = field(default_factory=list)


def _t(en: str, ur: str, roman: str) -> dict[str, str]:
    return {"en": en, "ur": ur, "roman": roman}


RULES: dict[str, RuleInfo] = {
    r.id: r
    for r in [
        RuleInfo(
            "secret_request", 45,
            _t("Asks for your OTP, PIN or password",
               "آپ سے OTP، پن یا پاس ورڈ مانگا گیا ہے",
               "Aap se OTP, PIN ya password manga gaya hai"),
            _t("Banks, wallets and government offices never ask for these codes. Whoever has them can empty your account or take over your WhatsApp.",
               "بینک، والیٹ اور سرکاری ادارے کبھی یہ کوڈ نہیں مانگتے۔ جس کے پاس یہ کوڈ ہو وہ آپ کا اکاؤنٹ خالی کر سکتا ہے یا واٹس ایپ پر قبضہ کر سکتا ہے۔",
               "Bank, wallet aur sarkari idaray yeh code kabhi nahi mangte. Jis ke paas yeh code ho woh aap ka account khali kar sakta hai ya WhatsApp le sakta hai."),
        ),
        RuleInfo(
            "code_hijack", 50,
            _t("Says a code was sent to you \"by mistake\"",
               "کہا گیا ہے کہ کوڈ \"غلطی سے\" آپ کو بھیجا گیا",
               "Kaha gaya hai ke code \"ghalti se\" aap ko bheja gaya"),
            _t("This is how WhatsApp and wallet accounts get stolen. That code is the login code for your own account.",
               "واٹس ایپ اور والیٹ اکاؤنٹ اسی طرح چرائے جاتے ہیں۔ وہ کوڈ دراصل آپ کے اپنے اکاؤنٹ کا لاگ اِن کوڈ ہے۔",
               "WhatsApp aur wallet accounts isi tarah chori hote hain. Woh code asal mein aap ke apne account ka login code hai."),
        ),
        RuleInfo(
            "fee_request", 30,
            _t("Asks you to pay a fee first",
               "پہلے فیس ادا کرنے کو کہا گیا ہے",
               "Pehle fee ada karne ko kaha gaya hai"),
            _t("Real prizes, government payments, loans and jobs do not ask for a fee before paying you.",
               "اصلی انعام، سرکاری رقم، قرض یا نوکری کے لیے پہلے فیس نہیں مانگی جاتی۔",
               "Asli inaam, sarkari raqam, qarz ya naukri ke liye pehle fee nahi mangi jati."),
        ),
        RuleInfo(
            "advance_fee", 15,
            _t("Wants a fee before releasing money, a prize or a parcel",
               "رقم، انعام یا پارسل دینے سے پہلے فیس مانگی گئی ہے",
               "Raqam, inaam ya parcel dene se pehle fee mangi gayi hai"),
            _t("Paying to unlock money you were promised is the classic advance-fee scam. The promised money never arrives.",
               "وعدہ کی گئی رقم کے لیے پہلے فیس دینا مشہور ایڈوانس فیس فراڈ ہے۔ وہ رقم کبھی نہیں آتی۔",
               "Wada ki gayi raqam ke liye pehle fee dena mashoor advance fee fraud hai. Woh raqam kabhi nahi aati."),
        ),
        RuleInfo(
            "money_transfer", 20,
            _t("Asks you to send money to a wallet or account",
               "کسی والیٹ یا اکاؤنٹ میں پیسے بھیجنے کو کہا گیا ہے",
               "Kisi wallet ya account mein paise bhejne ko kaha gaya hai"),
            _t("Money sent to a JazzCash, Easypaisa or bank account is very hard to get back once it is gone.",
               "جاز کیش، ایزی پیسہ یا بینک اکاؤنٹ میں بھیجی گئی رقم واپس ملنا بہت مشکل ہوتا ہے۔",
               "JazzCash, Easypaisa ya bank account mein bheji gayi raqam wapas milna bohat mushkil hota hai."),
        ),
        RuleInfo(
            "prize", 20,
            _t("Says you have won a prize or reward",
               "کہا گیا ہے کہ آپ نے انعام جیتا ہے",
               "Kaha gaya hai ke aap ne inaam jeeta hai"),
            _t("Prize messages for draws you never entered are one of the most common scams.",
               "ایسی قرعہ اندازی کا انعام جس میں آپ نے حصہ ہی نہیں لیا، سب سے عام فراڈ میں سے ایک ہے۔",
               "Aisi qura andazi ka inaam jis mein aap ne hissa hi nahi liya, sab se aam fraud mein se ek hai."),
        ),
        RuleInfo(
            "prize_with_contact", 15,
            _t("Wants you to claim the prize through a number or link",
               "انعام لینے کے لیے کسی نمبر یا لنک پر رابطہ کرنے کو کہا گیا ہے",
               "Inaam lene ke liye kisi number ya link par rabta karne ko kaha gaya hai"),
            _t("Claiming through a number or link in the message is how the scammer reaches you next.",
               "پیغام میں دیے گئے نمبر یا لنک کے ذریعے ہی فراڈ کرنے والا آپ تک پہنچتا ہے۔",
               "Message mein diye gaye number ya link ke zariye hi fraud karne wala aap tak pohanchta hai."),
        ),
        RuleInfo(
            "personal_info_request", 35,
            _t("Asks for your CNIC, card or account details",
               "شناختی کارڈ، کارڈ یا اکاؤنٹ کی تفصیل مانگی گئی ہے",
               "CNIC, card ya account ki details mangi gayi hain"),
            _t("These details let someone open accounts or SIMs in your name, or pass bank checks as you.",
               "ان تفصیلات سے کوئی آپ کے نام پر اکاؤنٹ یا سم نکلوا سکتا ہے۔",
               "In details se koi aap ke naam par account ya SIM nikalwa sakta hai."),
        ),
        RuleInfo(
            "remote_app", 40,
            _t("Asks you to install an app or share your screen",
               "کوئی ایپ انسٹال کرنے یا اسکرین شیئر کرنے کو کہا گیا ہے",
               "Koi app install karne ya screen share karne ko kaha gaya hai"),
            _t("Screen-sharing apps like AnyDesk let the other person see your codes and control your phone.",
               "اینی ڈیسک جیسی ایپس سے دوسرا شخص آپ کے کوڈ دیکھ سکتا ہے اور فون چلا سکتا ہے۔",
               "AnyDesk jaisi apps se doosra shakhs aap ke code dekh sakta hai aur phone chala sakta hai."),
        ),
        RuleInfo(
            "family_emergency", 30,
            _t("Claims to be family in trouble and asks for money",
               "خود کو مشکل میں پھنسا رشتہ دار بتا کر پیسے مانگے گئے ہیں",
               "Khud ko mushkil mein phansa rishtedar bata kar paise mange gaye hain"),
            _t("Call the person on the number you already have for them before sending anything.",
               "کچھ بھیجنے سے پہلے اس شخص کو اس نمبر پر کال کریں جو پہلے سے آپ کے پاس ہے۔",
               "Kuch bhejne se pehle us shakhs ko us number par call karein jo pehle se aap ke paas hai."),
        ),
        RuleInfo(
            "too_good", 25,
            _t("Promises easy or guaranteed money",
               "آسان یا یقینی کمائی کا وعدہ کیا گیا ہے",
               "Asaan ya yaqeeni kamai ka wada kiya gaya hai"),
            _t("Guaranteed profit, daily earnings and \"double your money\" offers are how investment scams start.",
               "یقینی منافع اور \"پیسے ڈبل\" کرنے کی پیشکش سے ہی سرمایہ کاری کا فراڈ شروع ہوتا ہے۔",
               "Yaqeeni munafa aur \"paise double\" karne ki offer se hi investment fraud shuru hota hai."),
        ),
        RuleInfo(
            "guaranteed_returns", 55,
            _t("Promises guaranteed or doubled returns",
               "یقینی یا دگنے منافع کا وعدہ کیا گیا ہے",
               "Yaqeeni ya double munafe ka wada kiya gaya hai"),
            _t("No real investment can guarantee profit or double your money. This is how Ponzi and crypto scams pull people in.",
               "کوئی اصلی سرمایہ کاری منافع کی ضمانت یا پیسے ڈبل نہیں کر سکتی۔ پونزی اور کرپٹو فراڈ اسی طرح لوگوں کو پھنساتے ہیں۔",
               "Koi asli investment munafe ki guarantee ya paise double nahi kar sakti. Ponzi aur crypto fraud isi tarah logon ko phansate hain."),
        ),
        RuleInfo(
            "secrecy", 10,
            _t("Asks you to keep it secret",
               "بات چھپانے کو کہا گیا ہے",
               "Baat chhupane ko kaha gaya hai"),
            _t("Scammers ask for secrecy so no one can warn you. Talk to someone you trust before acting.",
               "فراڈ کرنے والے راز رکھنے کو کہتے ہیں تاکہ کوئی آپ کو خبردار نہ کر سکے۔ کچھ کرنے سے پہلے کسی قابل اعتماد شخص سے بات کریں۔",
               "Fraud karne wale raaz rakhne ko kehte hain taake koi aap ko khabardar na kar sake. Kuch karne se pehle kisi bharosemand shakhs se baat karein."),
        ),
        RuleInfo(
            "login_link", 20,
            _t("Asks you to log in or verify through a link",
               "لنک کے ذریعے لاگ اِن یا تصدیق کرنے کو کہا گیا ہے",
               "Link ke zariye login ya tasdeeq karne ko kaha gaya hai"),
            _t("Fake login pages copy real ones to steal passwords. Open the official app or type the website address yourself.",
               "جعلی لاگ اِن صفحات اصلی جیسے بنائے جاتے ہیں تاکہ پاس ورڈ چرائے جا سکیں۔ سرکاری ایپ کھولیں یا ویب سائٹ کا پتہ خود لکھیں۔",
               "Jaali login pages asli jaise banaye jate hain taake password chori ho sakein. Official app kholein ya website ka address khud likhein."),
        ),
        RuleInfo(
            "job_with_payment", 25,
            _t("Job or task offer that needs you to pay",
               "ایسی نوکری یا ٹاسک جس کے لیے آپ سے پیسے مانگے گئے ہیں",
               "Aisi naukri ya task jis ke liye aap se paise mange gaye hain"),
            _t("Real employers pay you; they do not charge registration, training or visa fees up front.",
               "اصلی کمپنی آپ کو تنخواہ دیتی ہے، پہلے رجسٹریشن یا ویزا فیس نہیں لیتی۔",
               "Asli company aap ko tankhwah deti hai, pehle registration ya visa fee nahi leti."),
        ),
        RuleInfo(
            "job_offer", 8,
            _t("Unexpected job or earning offer",
               "اچانک نوکری یا کمائی کی پیشکش",
               "Achanak naukri ya kamai ki offer"),
            _t("Unsolicited job offers over SMS or WhatsApp often turn into task or advance-fee scams.",
               "ایس ایم ایس یا واٹس ایپ پر اچانک نوکری کی پیشکش اکثر فراڈ بن جاتی ہے۔",
               "SMS ya WhatsApp par achanak naukri ki offer aksar fraud ban jati hai."),
        ),
        RuleInfo(
            "loan_with_fee", 15,
            _t("Loan offer that asks for a fee first",
               "قرض کی پیشکش جس کے لیے پہلے فیس مانگی گئی ہے",
               "Qarz ki offer jis ke liye pehle fee mangi gayi hai"),
            _t("Lenders deduct charges from the loan; they do not ask you to pay before you receive it.",
               "قرض دینے والے ادارے فیس قرض میں سے کاٹتے ہیں، پہلے نہیں مانگتے۔",
               "Qarz dene wale idaray fee qarz mein se kaat-te hain, pehle nahi mangte."),
        ),
        RuleInfo(
            "delivery_bait", 10,
            _t("Parcel message that wants a fee or an address update by link",
               "پارسل کا پیغام جس میں فیس یا لنک پر پتہ اپڈیٹ کرنے کو کہا گیا ہے",
               "Parcel ka message jis mein fee ya link par address update karne ko kaha gaya hai"),
            _t("Couriers do not hold parcels for small fees paid through SMS links.",
               "کوریئر کمپنیاں ایس ایم ایس لنک کے ذریعے چھوٹی فیس کے لیے پارسل نہیں روکتیں۔",
               "Courier companiyan SMS link ke zariye choti fee ke liye parcel nahi roktin."),
        ),
        RuleInfo(
            "urgency", 10,
            _t("Pushes you to act immediately",
               "فوراً کچھ کرنے پر زور دیا گیا ہے",
               "Foran kuch karne par zor diya gaya hai"),
            _t("Rushing you is meant to stop you from checking with someone first.",
               "جلدی اس لیے مچائی جاتی ہے تاکہ آپ کسی سے پوچھ نہ سکیں۔",
               "Jaldi is liye machai jati hai taake aap kisi se pooch na sakein."),
        ),
        RuleInfo(
            "threat", 15,
            _t("Threatens to block your account or take action",
               "اکاؤنٹ بند کرنے یا کارروائی کی دھمکی دی گئی ہے",
               "Account band karne ya karwai ki dhamki di gayi hai"),
            _t("Fear makes people skip normal caution. Real organisations do not threaten you over SMS.",
               "ڈر کی وجہ سے لوگ احتیاط بھول جاتے ہیں۔ اصلی ادارے ایس ایم ایس پر دھمکیاں نہیں دیتے۔",
               "Dar ki wajah se log ehtiyat bhool jate hain. Asli idaray SMS par dhamkiyan nahi dete."),
        ),
        RuleInfo(
            "claims_government", 10,
            _t("Claims to come from a government office or programme",
               "سرکاری ادارے یا پروگرام کی طرف سے ہونے کا دعویٰ",
               "Sarkari idaray ya program ki taraf se hone ka daawa"),
            _t("Scammers borrow names like BISP, NADRA and FBR because people trust them.",
               "فراڈ کرنے والے بی آئی ایس پی، نادرا اور ایف بی آر جیسے نام استعمال کرتے ہیں کیونکہ لوگ ان پر بھروسہ کرتے ہیں۔",
               "Fraud karne wale BISP, NADRA aur FBR jaise naam use karte hain kyunke log in par bharosa karte hain."),
        ),
        RuleInfo(
            "bisp_wrong_sender", 35,
            _t("BISP message that did not come from 8171",
               "بی آئی ایس پی کا پیغام جو 8171 سے نہیں آیا",
               "BISP ka message jo 8171 se nahi aya"),
            _t("BISP says its official messages come only from 8171. Messages from other numbers are fake.",
               "بی آئی ایس پی کے مطابق اس کے سرکاری پیغامات صرف 8171 سے آتے ہیں۔ کسی اور نمبر سے آنے والا پیغام جعلی ہے۔",
               "BISP ke mutabiq us ke sarkari messages sirf 8171 se aate hain. Kisi aur number se aane wala message jaali hai."),
        ),
        RuleInfo(
            "claims_bank", 5,
            _t("Claims to come from a bank or wallet",
               "بینک یا والیٹ کی طرف سے ہونے کا دعویٰ",
               "Bank ya wallet ki taraf se hone ka daawa"),
            _t("On its own this is normal; it matters when combined with requests for codes, money or links.",
               "یہ اکیلا مسئلہ نہیں، لیکن کوڈ، پیسے یا لنک کے مطالبے کے ساتھ ہو تو خطرہ ہے۔",
               "Yeh akela masla nahi, lekin code, paise ya link ke mutalbe ke saath ho to khatra hai."),
        ),
        RuleInfo(
            "sender_mismatch", 25,
            _t("Official-sounding message from a personal mobile number",
               "سرکاری یا بینک کا پیغام کسی عام موبائل نمبر سے",
               "Sarkari ya bank ka message kisi aam mobile number se"),
            _t("Banks, wallets and government offices send SMS from short codes or names, not from 03xx numbers.",
               "بینک، والیٹ اور سرکاری ادارے شارٹ کوڈ یا نام سے ایس ایم ایس بھیجتے ہیں، 03 والے نمبروں سے نہیں۔",
               "Bank, wallet aur sarkari idaray short code ya naam se SMS bhejte hain, 03 wale numbers se nahi."),
        ),
        RuleInfo(
            "call_request", 20,
            _t("Asks you to call or message a number given in the text",
               "پیغام میں دیے گئے نمبر پر رابطہ کرنے کو کہا گیا ہے",
               "Message mein diye gaye number par rabta karne ko kaha gaya hai"),
            _t("Use the helpline on your card or the official website instead of a number in the message.",
               "پیغام والے نمبر کی بجائے کارڈ کے پیچھے لکھا یا سرکاری ویب سائٹ والا نمبر استعمال کریں۔",
               "Message wale number ki bajaye card ke peeche likha ya official website wala number use karein."),
        ),
        RuleInfo(
            "link_lookalike", 40,
            _t("Link imitates {brand}'s website",
               "لنک {brand} کی ویب سائٹ کی نقل ہے",
               "Link {brand} ki website ki naqal hai"),
            _t("The address looks like {brand} but is a different website ({domain}). {brand}'s real site is {official}.",
               "یہ پتہ {brand} جیسا لگتا ہے لیکن یہ ایک دوسری ویب سائٹ ({domain}) ہے۔ {brand} کی اصل ویب سائٹ {official} ہے۔",
               "Yeh address {brand} jaisa lagta hai lekin yeh doosri website ({domain}) hai. {brand} ki asli website {official} hai."),
        ),
        RuleInfo(
            "link_not_official", 25,
            _t("Link does not belong to {brand}",
               "لنک {brand} کا نہیں ہے",
               "Link {brand} ka nahi hai"),
            _t("The message claims to be from {brand}, but the link goes to {domain}. {brand}'s real site is {official}.",
               "پیغام {brand} کی طرف سے ہونے کا دعویٰ کرتا ہے لیکن لنک {domain} پر جاتا ہے۔ {brand} کی اصل ویب سائٹ {official} ہے۔",
               "Message {brand} ki taraf se hone ka daawa karta hai lekin link {domain} par jata hai. {brand} ki asli website {official} hai."),
        ),
        RuleInfo(
            "link_safe_browsing", 60,
            _t("Google Safe Browsing lists this link as dangerous",
               "گوگل سیف براؤزنگ نے اس لنک کو خطرناک قرار دیا ہے",
               "Google Safe Browsing ne is link ko khatarnak qarar diya hai"),
            _t("This link is on Google's list of phishing or malware sites.",
               "یہ لنک گوگل کی فشنگ یا میلویئر ویب سائٹس کی فہرست میں ہے۔",
               "Yeh link Google ki phishing ya malware websites ki list mein hai."),
        ),
        RuleInfo(
            "link_new_domain", 25,
            _t("The linked website is only {days} days old",
               "لنک والی ویب سائٹ صرف {days} دن پرانی ہے",
               "Link wali website sirf {days} din purani hai"),
            _t("Scam sites are usually registered days before a campaign and abandoned soon after.",
               "فراڈ ویب سائٹس عموماً چند دن پہلے بنائی جاتی ہیں اور جلد چھوڑ دی جاتی ہیں۔",
               "Fraud websites aam tor par chand din pehle banai jati hain aur jald chhor di jati hain."),
        ),
        RuleInfo(
            "link_shortener", 12,
            _t("Link is hidden behind a URL shortener",
               "لنک کو شارٹنر کے پیچھے چھپایا گیا ہے",
               "Link ko shortener ke peeche chhupaya gaya hai"),
            _t("Shorteners hide where a link really goes. Official SMS rarely use them.",
               "شارٹنر اصل منزل چھپا دیتا ہے۔ سرکاری پیغامات میں یہ کم ہی استعمال ہوتا ہے۔",
               "Shortener asal manzil chhupa deta hai. Official messages mein yeh kam hi use hota hai."),
        ),
        RuleInfo(
            "link_risky_tld", 10,
            _t("Link uses a domain ending common in scams (.{tld})",
               "لنک ایسے ڈومین (.{tld}) پر ہے جو فراڈ میں عام ہے",
               "Link aise domain (.{tld}) par hai jo fraud mein aam hai"),
            _t("Endings like .xyz and .top are cheap to register and heavily used for SMS phishing.",
               "‎.xyz اور ‎.top جیسے ڈومین سستے ہوتے ہیں اور فشنگ میں بہت استعمال ہوتے ہیں۔",
               ".xyz aur .top jaise domain saste hote hain aur phishing mein bohat use hote hain."),
        ),
        RuleInfo(
            "link_raw_ip", 20,
            _t("Link points to a bare IP address",
               "لنک کسی ویب سائٹ کے نام کی بجائے آئی پی ایڈریس پر ہے",
               "Link kisi website ke naam ki bajaye IP address par hai"),
            _t("Legitimate services use named websites, not raw IP addresses.",
               "اصلی سروسز نام والی ویب سائٹ استعمال کرتی ہیں، آئی پی ایڈریس نہیں۔",
               "Asli services naam wali website use karti hain, IP address nahi."),
        ),
        RuleInfo(
            "link_punycode", 20,
            _t("Link uses look-alike characters",
               "لنک میں ملتے جلتے حروف استعمال ہوئے ہیں",
               "Link mein milte julte huroof use hue hain"),
            _t("Addresses starting with xn-- can show letters from other alphabets that look identical to English ones.",
               "xn-- والے پتے دوسری زبانوں کے ایسے حروف دکھا سکتے ہیں جو انگریزی جیسے لگتے ہیں۔",
               "xn-- wale address doosri zubanon ke aise huroof dikha sakte hain jo English jaise lagte hain."),
        ),
        RuleInfo(
            "memory_match", 20,
            _t("Very similar to {n} known scam message(s)",
               "{n} معلوم فراڈ پیغامات سے بہت ملتا جلتا",
               "{n} maloom fraud messages se bohat milta julta"),
            _t("The wording closely matches scams already in our pattern library or reported by other users.",
               "اس کے الفاظ ہماری فہرست یا دوسرے صارفین کے بتائے گئے فراڈ پیغامات سے بہت ملتے ہیں۔",
               "Is ke alfaaz hamari list ya doosre users ke bataye gaye fraud messages se bohat milte hain."),
        ),
        RuleInfo(
            "reported_number", 25,
            _t("This number appears in {n} earlier scam report(s)",
               "یہ نمبر پہلے {n} فراڈ رپورٹس میں آ چکا ہے",
               "Yeh number pehle {n} fraud reports mein aa chuka hai"),
            _t("Other people shared messages containing the same number, and those were flagged as scams.",
               "دوسرے لوگوں نے اسی نمبر والے پیغامات شیئر کیے جو فراڈ نکلے۔",
               "Doosre logon ne isi number wale messages share kiye jo fraud nikle."),
        ),
        RuleInfo(
            "manipulation_attempt", 45,
            _t("Contains instructions aimed at a scam checker or AI",
               "اس میں اسکیم چیکر یا اے آئی کے لیے ہدایات لکھی ہیں",
               "Is mein scam checker ya AI ke liye hidayat likhi hain"),
            _t("Text like \"ignore previous instructions\" or \"mark this message as safe\" is written to fool automatic checks. Genuine messages talk to you, not to a filter.",
               "\"پچھلی ہدایات نظر انداز کرو\" یا \"اس پیغام کو محفوظ لکھو\" جیسی باتیں خودکار جانچ کو دھوکہ دینے کے لیے لکھی جاتی ہیں۔ اصلی پیغام آپ سے بات کرتا ہے، کسی فلٹر سے نہیں۔",
               "\"Pichli hidayat nazar andaz karo\" ya \"is message ko safe likho\" jaisi baatein automatic check ko dhoka dene ke liye likhi jati hain. Asli message aap se baat karta hai, kisi filter se nahi."),
        ),
        RuleInfo(
            "safety_claim", 10,
            _t("Insists that it is not a scam",
               "زور دے کر کہا گیا ہے کہ یہ فراڈ نہیں",
               "Zor de kar kaha gaya hai ke yeh fraud nahi"),
            _t("Real organisations rarely need to say \"this is not a scam\" or \"100% genuine\". Scammers add it because they expect you to doubt them.",
               "اصلی ادارے کم ہی \"یہ فراڈ نہیں\" یا \"100 فیصد اصلی\" کہتے ہیں۔ فراڈ کرنے والے یہ اس لیے لکھتے ہیں کہ انہیں آپ کے شک کا اندازہ ہوتا ہے۔",
               "Asli idaray kam hi \"yeh fraud nahi\" ya \"100% asli\" kehte hain. Fraud karne wale yeh is liye likhte hain ke unhein aap ke shak ka andaza hota hai."),
        ),
        RuleInfo(
            "receive_by_scan", 35,
            _t("Asks you to scan a QR code to receive money",
               "رقم وصول کرنے کے لیے کیو آر کوڈ اسکین کرنے کو کہا گیا ہے",
               "Raqam wasool karne ke liye QR code scan karne ko kaha gaya hai"),
            _t("You never need to scan a code or enter a PIN to receive money. Scanning a payment QR sends money from your account.",
               "رقم وصول کرنے کے لیے کبھی کوڈ اسکین کرنے یا پن ڈالنے کی ضرورت نہیں ہوتی۔ پیمنٹ کیو آر اسکین کرنے سے آپ کے اکاؤنٹ سے پیسے جاتے ہیں۔",
               "Raqam wasool karne ke liye kabhi code scan karne ya PIN dalne ki zaroorat nahi hoti. Payment QR scan karne se aap ke account se paise jate hain."),
        ),
        RuleInfo(
            "fake_credit_alert", 45,
            _t("\"Money received\" message from an ordinary mobile number",
               "عام موبائل نمبر سے \"رقم موصول\" کا پیغام",
               "Aam mobile number se \"raqam mosool\" ka message"),
            _t("JazzCash, Easypaisa and banks send these alerts from short codes or their own name, never from a 03xx number. "
               "Open your app and check your balance before doing anything.",
               "جاز کیش، ایزی پیسہ اور بینک یہ پیغام شارٹ کوڈ یا اپنے نام سے بھیجتے ہیں، کبھی 03 والے نمبر سے نہیں۔ "
               "کچھ کرنے سے پہلے اپنی ایپ کھول کر بیلنس دیکھیں۔",
               "JazzCash, Easypaisa aur bank yeh message short code ya apne naam se bhejte hain, kabhi 03 wale number se nahi. "
               "Kuch karne se pehle apni app khol kar balance dekhein."),
        ),
        RuleInfo(
            "refund_trick", 45,
            _t("Says money was sent to you \"by mistake\" and asks for it back",
               "کہا گیا ہے کہ پیسے \"غلطی سے\" آپ کو بھیجے گئے، واپس کریں",
               "Kaha gaya hai ke paise \"ghalti se\" aap ko bheje gaye, wapas karein"),
            _t("A common trick: a fake \"money received\" message, then a call asking you to return it. Check your balance in the "
               "app. If money really arrived by mistake, the wallet's helpline reverses it; never send it back yourself.",
               "عام چال: جعلی \"رقم موصول\" کا پیغام، پھر واپس کرنے کی کال۔ ایپ میں بیلنس دیکھیں۔ اگر واقعی غلطی سے "
               "رقم آئی ہو تو والیٹ کی ہیلپ لائن اسے واپس کرتی ہے؛ خود واپس نہ بھیجیں۔",
               "Aam chaal: jaali \"raqam mosool\" ka message, phir wapas karne ki call. App mein balance dekhein. Agar waqai "
               "ghalti se raqam aayi ho to wallet ki helpline usay wapas karti hai; khud wapas na bhejein."),
        ),
        RuleInfo(
            "passport_request", 25,
            _t("Asks you to send or hand over your passport",
               "پاسپورٹ بھیجنے یا جمع کروانے کو کہا گیا ہے",
               "Passport bhejne ya jama karwane ko kaha gaya hai"),
            _t("The Bureau of Emigration says showing your original passport for identification is enough; do not leave it with a test centre or agent.",
               "بیورو آف امیگریشن کے مطابق شناخت کے لیے اصل پاسپورٹ دکھانا کافی ہے؛ اسے کسی ٹیسٹ سینٹر یا ایجنٹ کے پاس نہ چھوڑیں۔",
               "Bureau of Emigration ke mutabiq shanakht ke liye asal passport dikhana kaafi hai; ise kisi test centre ya agent ke paas na chhorein.")
        ),
        RuleInfo(
            "mixed_script", 20,
            _t("Uses look-alike letters from another alphabet",
               "دوسری زبان کے ملتے جلتے حروف استعمال کیے گئے ہیں",
               "Doosri zuban ke milte julte huroof use kiye gaye hain"),
            _t("Words like {words} mix English letters with Cyrillic or Greek ones that look the same. This is done to slip past filters.",
               "{words} جیسے الفاظ میں انگریزی حروف کے ساتھ ملتے جلتے روسی یا یونانی حروف ملائے گئے ہیں تاکہ فلٹر سے بچا جا سکے۔",
               "{words} jaise alfaaz mein English huroof ke saath milte julte Russi ya Unani huroof milaye gaye hain taake filter se bacha ja sake."),
        ),
        RuleInfo(
            "watchlist_match", 60,
            _t("Matches the analysts' watchlist ({label})",
               "تجزیہ کاروں کی واچ لسٹ میں موجود ({label})",
               "Analysts ki watchlist mein mojood ({label})"),
            _t("A reviewer has already confirmed this as part of a scam campaign.",
               "ایک جائزہ کار پہلے ہی اس کی تصدیق کر چکا ہے کہ یہ فراڈ مہم کا حصہ ہے۔",
               "Ek reviewer pehle hi tasdeeq kar chuka hai ke yeh fraud muhim ka hissa hai.")
        ),
        RuleInfo(
            "reported_account", 25,
            _t("This bank account appears in {n} earlier scam report(s)",
               "یہ بینک اکاؤنٹ پہلے {n} فراڈ رپورٹس میں آ چکا ہے",
               "Yeh bank account pehle {n} fraud reports mein aa chuka hai"),
            _t("Other people reported messages asking for money to the same account.",
               "دوسرے لوگوں نے اسی اکاؤنٹ میں پیسے مانگنے والے پیغامات رپورٹ کیے ہیں۔",
               "Doosre logon ne isi account mein paise mangne wale messages report kiye hain."),
        ),
        RuleInfo(
            "email_auth_failed", 30,
            _t("The email failed sender checks ({checks})",
               "ای میل بھیجنے والے کی تصدیق میں ناکام رہی ({checks})",
               "Email bhejne wale ki tasdeeq mein nakam rahi ({checks})"),
            _t("The receiving mail server could not confirm that the email really came from the address it shows.",
               "وصول کرنے والا میل سرور تصدیق نہیں کر سکا کہ ای میل واقعی اسی پتے سے آئی ہے جو دکھایا گیا ہے۔",
               "Receive karne wala mail server tasdeeq nahi kar saka ke email waqai usi address se aayi hai jo dikhaya gaya hai."),
        ),
        RuleInfo(
            "email_brand_mismatch", 40,
            _t("Claims to be {brand} but was sent from {domain}",
               "{brand} ہونے کا دعویٰ مگر ای میل {domain} سے آئی",
               "{brand} hone ka daawa magar email {domain} se aayi"),
            _t("Emails from {brand} come from its own domain ({official}). The sender's real address is on {domain}.",
               "{brand} کی ای میلز اس کے اپنے ڈومین ({official}) سے آتی ہیں۔ بھیجنے والے کا اصل پتہ {domain} پر ہے۔",
               "{brand} ki emails us ke apne domain ({official}) se aati hain. Bhejne wale ka asal address {domain} par hai."),
        ),
        RuleInfo(
            "email_freemail_brand", 35,
            _t("An organisation's name on a free email account",
               "مفت ای میل اکاؤنٹ پر کسی ادارے کا نام",
               "Muft email account par kisi idaray ka naam"),
            _t("Banks, government offices and employers do not write from Gmail, Yahoo or Outlook addresses like {domain}.",
               "بینک، سرکاری ادارے اور کمپنیاں {domain} جیسے جی میل، یاہو یا آؤٹ لک پتوں سے ای میل نہیں کرتے۔",
               "Bank, sarkari idaray aur companiyan {domain} jaise Gmail, Yahoo ya Outlook addresses se email nahi karte."),
        ),
        RuleInfo(
            "email_reply_to_mismatch", 15,
            _t("Replies would go to a different address",
               "جواب کسی دوسرے پتے پر جائے گا",
               "Jawab kisi doosre address par jayega"),
            _t("The email shows one sender but replies go to {domain}. Scammers do this to receive your answers.",
               "ای میل ایک بھیجنے والا دکھاتی ہے لیکن جواب {domain} پر جاتا ہے۔ فراڈ کرنے والے آپ کا جواب لینے کے لیے ایسا کرتے ہیں۔",
               "Email ek bhejne wala dikhati hai lekin jawab {domain} par jata hai. Fraud karne wale aap ka jawab lene ke liye aisa karte hain."),
        ),
        RuleInfo(
            "risky_attachment", 35,
            _t("Contains a risky file ({files})",
               "خطرناک فائل شامل ہے ({files})",
               "Khatarnak file shamil hai ({files})"),
            _t("Files like APKs, programs, scripts and web pages can install malware or show a fake login page. Do not open them.",
               "اے پی کے، پروگرام، اسکرپٹ اور ویب پیج جیسی فائلیں وائرس انسٹال کر سکتی ہیں یا جعلی لاگ اِن صفحہ دکھا سکتی ہیں۔ انہیں نہ کھولیں۔",
               "APK, program, script aur web page jaisi files virus install kar sakti hain ya jaali login page dikha sakti hain. Inhein na kholein."),
        ),
        RuleInfo(
            "pdf_active_content", 35,
            _t("The PDF contains code or hidden files",
               "پی ڈی ایف میں کوڈ یا چھپی فائلیں ہیں",
               "PDF mein code ya chhupi files hain"),
            _t("Normal letters and invoices do not need scripts, auto-run actions or embedded files ({what}).",
               "عام خطوط اور بلوں میں اسکرپٹ، خودکار چلنے والے عمل یا اندر چھپی فائلوں ({what}) کی ضرورت نہیں ہوتی۔",
               "Aam khutoot aur bills mein script, khud-ba-khud chalne wale amal ya andar chhupi files ({what}) ki zaroorat nahi hoti."),
        ),
        RuleInfo(
            "safety_notice", -15,
            _t("Contains a standard \"never share your code\" warning",
               "اس میں عام \"اپنا کوڈ کسی کو نہ بتائیں\" والی تنبیہ ہے",
               "Is mein aam \"apna code kisi ko na batayen\" wali tanbeeh hai"),
            _t("Genuine OTP and alert messages usually include this warning.",
               "اصلی او ٹی پی اور الرٹ پیغامات میں عموماً یہ تنبیہ ہوتی ہے۔",
               "Asli OTP aur alert messages mein aam tor par yeh tanbeeh hoti hai."),
        ),
        RuleInfo(
            "official_links", -10,
            _t("Links go to the official {brand} website",
               "لنک {brand} کی اصل ویب سائٹ پر جاتے ہیں",
               "Links {brand} ki asli website par jate hain"),
            _t("Every link in the message points to a known official domain.",
               "پیغام کے تمام لنک معلوم سرکاری یا اصلی ڈومین پر ہیں۔",
               "Message ke tamam links maloom official domain par hain."),
        ),
    ]
}

_REQUEST_RULES = {
    "advance_fee", "guaranteed_returns", "login_link", "secret_request", "code_hijack", "fee_request", "money_transfer", "personal_info_request",
    "remote_app", "family_emergency", "link_lookalike", "link_safe_browsing", "link_new_domain",
    "link_not_official", "job_with_payment", "loan_with_fee", "manipulation_attempt", "watchlist_match",
    "receive_by_scan", "passport_request", "risky_attachment", "pdf_active_content", "email_brand_mismatch",
    "email_freemail_brand", "fake_credit_alert", "refund_trick",
}

# Where a signal can come from. Anything other than "ai" is deterministic.
DETERMINISTIC_SOURCES = {"pattern", "file-check", "sender", "link-check", "memory", "watchlist"}


def _sig_hit(ctx: EvalContext, rule_id: str, signal: str, hard: bool = False, params=None) -> RuleHit | None:
    s = ctx.signals.get(signal)
    if not s:
        return None
    info = RULES[rule_id]
    ai_only = not (s.sources - {"ai"})
    weight = round(info.weight * AI_ONLY_FACTOR) if ai_only else info.weight
    return RuleHit(
        id=rule_id,
        weight=weight,
        hard=hard and not ai_only,
        evidence=list(s.evidence),
        sources=sorted(s.sources),
        params=params or {},
    )


def _official_domain(brand_key: str) -> str:
    for b in BRANDS:
        if b.key == brand_key:
            return b.domains[0]
    return ""


def evaluate(ctx: EvalContext) -> list[RuleHit]:
    sig = ctx.signals
    hits: list[RuleHit] = []

    def add(hit: RuleHit | None) -> None:
        if hit:
            hits.append(hit)

    claims_authority = sig.has("claims_bank") or sig.has("claims_government")
    links = ctx.links
    has_link = bool(links)

    # --- Requests --------------------------------------------------------
    add(_sig_hit(ctx, "secret_request", "secret_request",
                 hard=claims_authority or has_link or sig.has("code_hijack") or bool(sig.brands)))
    add(_sig_hit(ctx, "code_hijack", "code_hijack", hard=True))
    add(_sig_hit(ctx, "fee_request", "fee_request"))
    if sig.has("fee_request") and any(
        sig.has(x) for x in ("prize", "refund", "claims_government", "delivery", "loan", "job_offer")
    ):
        add(_sig_hit(ctx, "advance_fee", "fee_request"))
    add(_sig_hit(ctx, "money_transfer", "money_transfer"))
    add(_sig_hit(ctx, "personal_info_request", "personal_info_request",
                 hard=claims_authority or has_link or sig.has("prize") or sig.has("refund")))
    add(_sig_hit(ctx, "remote_app", "remote_app", hard=claims_authority or sig.has("secret_request")))
    # "New number + asking for money" is the textbook family scam.
    add(_sig_hit(ctx, "family_emergency", "family_emergency", hard=sig.pattern_backed("new_number")))
    add(_sig_hit(ctx, "secrecy", "secrecy"))

    # --- Offers ----------------------------------------------------------
    add(_sig_hit(ctx, "prize", "prize"))
    if sig.has("prize") and (sig.has("has_phone") or has_link or sig.has("call_request")):
        add(RuleHit("prize_with_contact", RULES["prize_with_contact"].weight, sources=["pattern"]))
    add(_sig_hit(ctx, "guaranteed_returns", "guaranteed_returns"))
    add(_sig_hit(ctx, "too_good", "too_good"))
    paid = sig.has("fee_request") or sig.has("money_transfer")
    if sig.has("job_offer"):
        if paid:
            hit = _sig_hit(ctx, "job_with_payment", "job_offer")
            add(hit)
        else:
            add(_sig_hit(ctx, "job_offer", "job_offer"))
    if sig.has("loan") and sig.has("fee_request"):
        add(_sig_hit(ctx, "loan_with_fee", "loan"))
    if sig.has("delivery") and (sig.has("fee_request") or any(not lk.get("official_brand") for lk in links)):
        add(_sig_hit(ctx, "delivery_bait", "delivery"))

    # --- Pressure --------------------------------------------------------
    add(_sig_hit(ctx, "urgency", "urgency"))
    add(_sig_hit(ctx, "threat", "threat"))

    # --- Who it claims to be --------------------------------------------
    add(_sig_hit(ctx, "claims_government", "claims_government"))
    if not sig.has("claims_government"):
        add(_sig_hit(ctx, "claims_bank", "claims_bank"))
    if any(b.key == "bisp" for b in sig.brands) and ctx.sender and ctx.sender_kind != "unknown":
        from app.core.redaction import normalize_sender

        if normalize_sender(ctx.sender) != "8171":
            hits.append(RuleHit("bisp_wrong_sender", RULES["bisp_wrong_sender"].weight, hard=True,
                                evidence=[f"sender: {ctx.sender}"], sources=["sender"]))
    authority_kinds = {"bank", "wallet", "government", "telecom", "utility", "courier"}
    if ctx.sender_kind == "mobile" and (claims_authority or (sig.brand_kinds() & authority_kinds)):
        # If only the model thinks the message claims authority, this counts for less.
        pattern_claim = (sig.pattern_backed("claims_bank") or sig.pattern_backed("claims_government")
                         or bool(sig.brand_kinds() & authority_kinds))
        weight = RULES["sender_mismatch"].weight if pattern_claim else round(RULES["sender_mismatch"].weight * AI_ONLY_FACTOR)
        hits.append(RuleHit("sender_mismatch", weight,
                            evidence=[f"sender: {ctx.sender}"], sources=["sender"]))
    if sig.has("call_request") and (claims_authority or sig.brand_kinds() & authority_kinds or sig.has("prize")):
        add(_sig_hit(ctx, "call_request", "call_request"))

    # --- Links -----------------------------------------------------------
    claimed = [b for b in sig.brands if b.kind in ("bank", "wallet", "government", "courier", "utility", "telecom")]
    for link in links:
        dom = link.get("final_registered_domain") or link.get("registered_domain") or link.get("host", "")
        if link.get("safe_browsing_threats"):
            hits.append(RuleHit("link_safe_browsing", RULES["link_safe_browsing"].weight, hard=True,
                                evidence=[link["url"]], sources=["link-check"],
                                params={"domain": dom}))
        look = link.get("lookalike_brand")
        if look:
            hard = look.get("kind") in ("bank", "wallet", "government") or look.get("key") == "epay_punjab"
            hits.append(RuleHit("link_lookalike", RULES["link_lookalike"].weight, hard=hard,
                                evidence=[link["url"]], sources=["link-check"],
                                params={"brand": look["name"], "domain": dom,
                                        "official": _official_domain(look["key"])}))
        elif claimed and not link.get("official_brand"):
            # Includes short links: an organisation's real messages point to its own domain.
            b = claimed[0]
            hits.append(RuleHit("link_not_official", RULES["link_not_official"].weight,
                                evidence=[link["url"]], sources=["link-check"],
                                params={"brand": b.name, "domain": dom, "official": b.domains[0]}))
        age = link.get("domain_age_days")
        if age is not None and age < link.get("new_domain_days", 90) and not link.get("official_brand"):
            hits.append(RuleHit("link_new_domain", RULES["link_new_domain"].weight,
                                evidence=[dom], sources=["link-check"], params={"days": age}))
        if link.get("is_shortener") and not link.get("official_brand"):
            hits.append(RuleHit("link_shortener", RULES["link_shortener"].weight,
                                evidence=[link["url"]], sources=["link-check"]))
        if link.get("risky_tld") and not link.get("official_brand"):
            hits.append(RuleHit("link_risky_tld", RULES["link_risky_tld"].weight,
                                evidence=[dom], sources=["link-check"], params={"tld": link.get("suffix", "")}))
        if link.get("is_ip"):
            hits.append(RuleHit("link_raw_ip", RULES["link_raw_ip"].weight,
                                evidence=[link["url"]], sources=["link-check"]))
        if link.get("is_punycode"):
            hits.append(RuleHit("link_punycode", RULES["link_punycode"].weight,
                                evidence=[link["host"]], sources=["link-check"]))

    if sig.has("login_request") and any(not lk.get("official_brand") for lk in links):
        add(_sig_hit(ctx, "login_link", "login_request"))

    # --- Evasion and manipulation ----------------------------------------
    add(_sig_hit(ctx, "manipulation_attempt", "manipulation_attempt", hard=True))
    add(_sig_hit(ctx, "safety_claim", "safety_claim"))
    add(_sig_hit(ctx, "receive_by_scan", "receive_by_scan", hard=bool(sig.brands) or sig.has("prize")))
    if sig.has("credit_alert") and ctx.sender_kind == "mobile" and sig.pattern_backed("credit_alert"):
        hits.append(RuleHit("fake_credit_alert", RULES["fake_credit_alert"].weight, hard=True,
                            evidence=list(sig.get("credit_alert").evidence) + [f"sender: {ctx.sender}"],
                            sources=["pattern", "sender"]))
    add(_sig_hit(ctx, "refund_trick", "mistaken_payment",
                 hard=sig.has("credit_alert") or sig.has("money_transfer") or ctx.sender_kind == "mobile"))
    add(_sig_hit(ctx, "passport_request", "passport_request"))
    mixed = sig.get("mixed_script")
    if mixed:
        add(_sig_hit(ctx, "mixed_script", "mixed_script", params={"words": mixed.evidence[0] if mixed.evidence else ""}))

    # --- Files and emails (signals added by the file readers) ------------
    auth = sig.get("email_auth_failed")
    if auth:
        add(_sig_hit(ctx, "email_auth_failed", "email_auth_failed", params={"checks": auth.evidence[0] if auth.evidence else ""}))
    mismatch = sig.get("email_brand_mismatch")
    if mismatch and mismatch.evidence:
        brand_key, _, domain = mismatch.evidence[0].partition("|")
        b = next((x for x in BRANDS if x.key == brand_key), None)
        if b:
            hit = _sig_hit(ctx, "email_brand_mismatch", "email_brand_mismatch",
                           hard=bool(auth) and b.kind in ("bank", "wallet", "government"),
                           params={"brand": b.name, "domain": domain, "official": b.domains[0]})
            if hit:
                hit.evidence = [f"{b.name} → {domain}"]
            add(hit)
    free = sig.get("email_freemail_brand")
    if free:
        add(_sig_hit(ctx, "email_freemail_brand", "email_freemail_brand", params={"domain": free.evidence[0] if free.evidence else ""}))
    reply = sig.get("email_reply_to_mismatch")
    if reply:
        add(_sig_hit(ctx, "email_reply_to_mismatch", "email_reply_to_mismatch", params={"domain": reply.evidence[0] if reply.evidence else ""}))
    files = sig.get("risky_attachment")
    if files:
        add(_sig_hit(ctx, "risky_attachment", "risky_attachment", hard=claims_authority or bool(sig.brands),
                     params={"files": ", ".join(files.evidence)}))
    active = sig.get("pdf_active_content")
    if active:
        add(_sig_hit(ctx, "pdf_active_content", "pdf_active_content", params={"what": ", ".join(active.evidence)}))

    # --- Watchlist (confirmed by a reviewer) -----------------------------
    for w in ctx.watchlist_hits[:3]:
        kind = {"domain": "website", "phone": "phone number", "account": "bank account"}.get(w.get("kind", ""), "item")
        hits.append(RuleHit("watchlist_match", RULES["watchlist_match"].weight, hard=True,
                            evidence=[w.get("label", "")], sources=["watchlist"],
                            params={"label": w.get("label", ""), "kind": kind}))
        break

    # --- Memory ----------------------------------------------------------
    scam_matches = [m for m in ctx.memory_matches if m.get("verdict") == "likely_scam"]
    if scam_matches:
        n = len(scam_matches)
        hits.append(RuleHit("memory_match", RULES["memory_match"].weight + (5 if n >= 3 else 0),
                            evidence=[m.get("excerpt", "")[:80] for m in scam_matches[:2]],
                            sources=["memory"], params={"n": n}))
    if ctx.reported_number_count:
        hits.append(RuleHit("reported_number", RULES["reported_number"].weight,
                            evidence=["phone number fingerprint match"], sources=["memory"],
                            params={"n": ctx.reported_number_count}))
    if ctx.reported_account_count:
        hits.append(RuleHit("reported_account", RULES["reported_account"].weight,
                            evidence=["account fingerprint match"], sources=["memory"],
                            params={"n": ctx.reported_account_count}))

    # --- Reassuring signs (only when nothing risky was found) ------------
    risky = {h.id for h in hits} & _REQUEST_RULES or any(h.hard for h in hits)
    if not risky:
        add(_sig_hit(ctx, "safety_notice", "safety_notice"))
        if links and all(lk.get("official_brand") for lk in links):
            names = sorted({lk["official_brand"]["name"] for lk in links})
            hits.append(RuleHit("official_links", RULES["official_links"].weight,
                                evidence=[lk["registered_domain"] for lk in links], sources=["link-check"],
                                params={"brand": ", ".join(names)}))
    return hits


def official_brand_dict(registered_domain: str, host: str = "") -> dict | None:
    b = official_brand_for(registered_domain, host)
    if b:
        return {"key": b.key, "name": b.name, "kind": b.kind}
    if is_government_domain(registered_domain):
        return {"key": "gov_pk", "name": "Government of Pakistan", "kind": "government"}
    return None

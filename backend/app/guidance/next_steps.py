"""What to do next. Deterministic, so advice never depends on a model's mood."""

from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[2] / "data" / "reporting_channels.yaml"


@lru_cache
def channels() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


def _s(id_: str, en: str, ur: str, roman: str, link: str | None = None, urgent: bool = False) -> dict:
    step = {"id": id_, "text": {"en": en, "ur": ur, "roman": roman}, "urgent": urgent}
    if link:
        step["link"] = link
    return step


def next_steps(verdict: str, category: str, brands: set[str] | None = None, tags: set[str] | None = None) -> list[dict]:
    """`brands` are organisations the message names; `tags` are extra topics such as "challan"."""
    brands = brands or set()
    tags = tags or set()
    ch = channels()
    if verdict == "no_red_flags":
        return [
            _s("stay_alert",
               "No common scam signs were found. If anything still feels off, contact the organisation using a number you already trust.",
               "عام فراڈ کی کوئی علامت نہیں ملی۔ پھر بھی شک ہو تو ادارے سے اس نمبر پر رابطہ کریں جو آپ کو پہلے سے معلوم ہو۔",
               "Aam fraud ki koi alamat nahi mili. Phir bhi shak ho to idaray se us number par rabta karein jo aap ko pehle se maloom ho."),
            _s("never_share",
               "Whatever the message says, never share an OTP, PIN or password.",
               "پیغام کچھ بھی کہے، او ٹی پی، پن یا پاس ورڈ کبھی کسی کو نہ بتائیں۔",
               "Message kuch bhi kahe, OTP, PIN ya password kabhi kisi ko na batayen."),
        ]

    steps = [
        _s("dont_engage",
           "Do not reply, call back, open the link or send money.",
           "جواب نہ دیں، واپس کال نہ کریں، لنک نہ کھولیں اور پیسے نہ بھیجیں۔",
           "Jawab na dein, wapas call na karein, link na kholein aur paise na bhejein.",
           urgent=True),
    ]

    if category == "account_takeover":
        steps.append(_s("two_step",
                        "If you already shared the code, turn on WhatsApp two-step verification now (Settings > Account > Two-step verification) and tell your contacts.",
                        "اگر کوڈ بتا چکے ہیں تو ابھی واٹس ایپ میں ٹو اسٹیپ ویریفکیشن آن کریں (Settings > Account > Two-step verification) اور اپنے رابطوں کو خبردار کریں۔",
                        "Agar code bata chuke hain to abhi WhatsApp mein two-step verification on karein (Settings > Account > Two-step verification) aur apne contacts ko khabardar karein.",
                        urgent=True))
    if "challan" in tags:
        e = ch["psca_echallan"]
        steps.append(_s("check_challan",
                        f"Check the challan yourself at {e['url'].removeprefix('https://')} or in the ePay Punjab app, using your vehicle number. Do not use a link or phone number from the message.",
                        f"چالان خود {e['url'].removeprefix('https://')} یا ای پے پنجاب ایپ میں اپنی گاڑی کے نمبر سے چیک کریں۔ پیغام میں دیا گیا لنک یا نمبر استعمال نہ کریں۔",
                        f"Challan khud {e['url'].removeprefix('https://')} ya ePay Punjab app mein apni gaari ke number se check karein. Message mein diya gaya link ya number use na karein.",
                        link=e["url"], urgent=True))
        steps.append(_s("pay_officially",
                        "If a challan is real, pay it only by entering the PSID in the official ePay Punjab app or your own bank or wallet app, never through a link or to a personal account.",
                        "اگر چالان اصلی ہو تو صرف ای پے پنجاب ایپ یا اپنی بینک یا والیٹ ایپ میں پی ایس آئی ڈی ڈال کر ادائیگی کریں، کسی لنک یا ذاتی اکاؤنٹ کے ذریعے کبھی نہیں۔",
                        "Agar challan asli ho to sirf ePay Punjab app ya apni bank ya wallet app mein PSID daal kar payment karein, kisi link ya personal account ke zariye kabhi nahi."))
        steps.append(_s("challan_sender",
                        "Punjab Safe Cities Authority says genuine e-challans come from an official short code, not from a personal 03xx or +92 number.",
                        "پنجاب سیف سٹیز اتھارٹی کے مطابق اصلی ای چالان سرکاری شارٹ کوڈ سے آتے ہیں، کسی ذاتی 03 یا +92 نمبر سے نہیں۔",
                        "Punjab Safe Cities Authority ke mutabiq asli e-challan official short code se aate hain, kisi personal 03 ya +92 number se nahi."))
    if category in ("bank_wallet", "account_takeover", "investment", "job_task", "loan", "prize", "family_emergency", "government_benefit", "government_notice", "delivery", "utility", "phishing_link"):
        steps.append(_s("call_bank",
                        "If you shared card details or a code, or sent money, call your bank or wallet on the number printed on your card or in its official app right away.",
                        "اگر کارڈ کی تفصیل یا کوڈ بتا دیا ہے یا پیسے بھیج دیے ہیں تو فوراً اپنے بینک یا والیٹ کو کارڈ کے پیچھے لکھے یا ایپ میں دیے گئے نمبر پر کال کریں۔",
                        "Agar card ki details ya code bata diya hai ya paise bhej diye hain to foran apne bank ya wallet ko card ke peeche likhe ya app mein diye gaye number par call karein.",
                        urgent=True))
    if "overseas_job" in tags:
        b, f = ch["beoe"], ch["fia_helpline"]
        steps.append(_s("beoe_verify",
                        f"Overseas job ads must come from a licensed Overseas Employment Promoter and carry a permission or tracking number. Verify both with the Bureau of Emigration at {b['url'].removeprefix('https://')} before paying anything. Trade test centres are not recruiters.",
                        f"بیرون ملک نوکری کا اشتہار صرف لائسنس یافتہ اوورسیز ایمپلائمنٹ پروموٹر دے سکتا ہے اور اس پر اجازت یا ٹریکنگ نمبر ہوتا ہے۔ کچھ بھی ادا کرنے سے پہلے دونوں کی تصدیق بیورو آف امیگریشن سے {b['url'].removeprefix('https://')} پر کریں۔ ٹریڈ ٹیسٹ سینٹر بھرتی ایجنسی نہیں ہوتے۔",
                        f"Bairoon mulk naukri ka ishtehar sirf licensed Overseas Employment Promoter de sakta hai aur us par permission ya tracking number hota hai. Kuch bhi ada karne se pehle dono ki tasdeeq Bureau of Emigration se {b['url'].removeprefix('https://')} par karein. Trade test centre recruitment agency nahi hote.",
                        link=b["url"], urgent=True))
        steps.append(_s("beoe_pay",
                        f"Pay only clearly stated official fees, get a receipt, and never send money to a personal bank account or wallet. Keep your passport; showing it is enough. Report anyone selling visas or jobs to the FIA ({f['phone']}).",
                        f"صرف واضح سرکاری فیس ادا کریں، رسید لیں، اور کبھی کسی ذاتی بینک اکاؤنٹ یا والیٹ میں پیسے نہ بھیجیں۔ پاسپورٹ اپنے پاس رکھیں، دکھانا کافی ہے۔ ویزا یا نوکری بیچنے والوں کی شکایت ایف آئی اے ({f['phone']}) کو کریں۔",
                        f"Sirf wazeh sarkari fee ada karein, raseed lein, aur kabhi kisi personal bank account ya wallet mein paise na bhejein. Passport apne paas rakhein, dikhana kaafi hai. Visa ya naukri bechne walon ki shikayat FIA ({f['phone']}) ko karein."))
    if category == "malicious_file" or "risky_file" in tags:
        steps.append(_s("dont_open_file",
                        "Do not open the attachment or turn on editing or macros. Delete it. If you already opened it, scan the device and change important passwords from another phone or computer.",
                        "منسلکہ فائل نہ کھولیں اور ایڈیٹنگ یا میکرو آن نہ کریں۔ اسے ڈیلیٹ کر دیں۔ اگر کھول چکے ہیں تو ڈیوائس اسکین کریں اور اہم پاس ورڈ کسی دوسرے فون یا کمپیوٹر سے بدلیں۔",
                        "Attachment na kholein aur editing ya macros on na karein. Ise delete kar dein. Agar khol chuke hain to device scan karein aur aham passwords kisi doosre phone ya computer se badlein.",
                        urgent=True))
    if "email" in tags:
        steps.append(_s("report_email",
                        "Use your email app's \"Report phishing\" or \"Report spam\" option so the provider can block the sender for others too.",
                        "اپنی ای میل ایپ میں \"Report phishing\" یا \"Report spam\" استعمال کریں تاکہ دوسروں کے لیے بھی بھیجنے والا بلاک ہو جائے۔",
                        "Apni email app mein \"Report phishing\" ya \"Report spam\" use karein taake doosron ke liye bhi bhejne wala block ho jaye."))
    if category == "family_emergency":
        steps.append(_s("verify_family",
                        "Call your relative on the number you already have for them, or ask a question only they would know.",
                        "اپنے رشتہ دار کو اس نمبر پر کال کریں جو پہلے سے آپ کے پاس ہے، یا ایسا سوال پوچھیں جس کا جواب صرف وہی جانتے ہوں۔",
                        "Apne rishtedar ko us number par call karein jo pehle se aap ke paas hai, ya aisa sawal poochein jis ka jawab sirf wohi jante hon."))
    if "bisp" in brands or (category == "government_benefit" and not brands):
        b = ch["bisp"]
        steps.append(_s("bisp_official",
                        f"BISP says its official SMS come only from {b['sms_shortcode']}. For questions call the BISP helpline {b['phone']}.",
                        f"بی آئی ایس پی کے مطابق سرکاری ایس ایم ایس صرف {b['sms_shortcode']} سے آتے ہیں۔ سوال کے لیے ہیلپ لائن {b['phone']} پر کال کریں۔",
                        f"BISP ke mutabiq sarkari SMS sirf {b['sms_shortcode']} se aate hain. Sawal ke liye helpline {b['phone']} par call karein."))
    if category in ("bank_wallet", "investment", "loan", "job_task"):
        s = ch["sbp"]
        steps.append(_s("sbp",
                        f"For banking or mobile-wallet fraud you can also call the State Bank of Pakistan helpline {s['phone']}.",
                        f"بینکنگ یا موبائل والیٹ فراڈ کے لیے اسٹیٹ بینک کی ہیلپ لائن {s['phone']} پر بھی کال کر سکتے ہیں۔",
                        f"Banking ya mobile wallet fraud ke liye State Bank ki helpline {s['phone']} par bhi call kar sakte hain."))

    n, p = ch["nccia"], ch["pta"]
    steps.append(_s("report_nccia",
                    f"Report online fraud to NCCIA at {n['url'].removeprefix('https://')}. Keep screenshots and the complaint number.",
                    f"آن لائن فراڈ کی شکایت این سی سی آئی اے کو {n['url'].removeprefix('https://')} پر کریں۔ اسکرین شاٹ اور شکایت نمبر سنبھال کر رکھیں۔",
                    f"Online fraud ki shikayat NCCIA ko {n['url'].removeprefix('https://')} par karein. Screenshots aur complaint number sambhal kar rakhein.",
                    link=n["url"]))
    steps.append(_s("report_pta",
                    f"Report the scam number to PTA at {p['url'].removeprefix('https://')} or {p['phone']} so the SIM can be blocked.",
                    f"دھوکہ دینے والا نمبر پی ٹی اے کو {p['url'].removeprefix('https://')} یا {p['phone']} پر رپورٹ کریں تاکہ سم بند ہو سکے۔",
                    f"Fraud wala number PTA ko {p['url'].removeprefix('https://')} ya {p['phone']} par report karein taake SIM band ho sake.",
                    link=p["url"]))
    steps.append(_s("warn_others",
                    "Warn family members, especially elders, about this message.",
                    "گھر والوں، خاص طور پر بزرگوں کو اس پیغام سے خبردار کریں۔",
                    "Ghar walon, khaas tor par buzurgon ko is message se khabardar karein."))
    return steps

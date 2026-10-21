import pytest

from app.core.redaction import redact, sender_kind
from app.rules.catalog import AI_ONLY_FACTOR, RULES, EvalContext
from app.rules.engine import assess, render_hit
from app.rules.signals import SignalSet, detect_signals


def run(text: str, sender: str | None = None, links: list | None = None):
    red = redact(text, "s")
    ctx = EvalContext(signals=detect_signals(red.text), links=links or [], sender=sender, sender_kind=sender_kind(sender))
    return assess(ctx)


@pytest.mark.parametrize(
    ("text", "sender", "verdict"),
    [
        ("Mubarak ho! BISP ki 25000 ki raqam aa gayi. Hasil karne ke liye 500 registration fee JazzCash karein 03001234567", "03001234567", "likely_scam"),
        ("Maine galti se aap ke number par 6 digit code bhej diya, please wapas bhej dein", None, "likely_scam"),
        ("Ammi ye mera naya number hai, foran 5000 easypaisa kar dein, mushkil mein hoon", None, "likely_scam"),
        ("If you do not share the code your account will be blocked today", None, "likely_scam"),
        ("Invest 10,000 and get guaranteed 20% profit every week. Double your money!", None, "likely_scam"),
        ("آپ کا انعام نکلا ہے۔ وصول کرنے کے لیے 1000 روپے فیس جمع کروائیں", None, "likely_scam"),
        ("Your HBL OTP is 482913. Do not share it with anyone.", "HBL", "no_red_flags"),
        ("Ammi main 7 baje tak ghar aa jaunga", None, "no_red_flags"),
        ("Bhai maine university ki fees jama karwa di hai, receipt bhej raha hoon", None, "no_red_flags"),
        ("Yaar 500 bhej de easypaisa pe, kal wapas kar dunga", None, "no_red_flags"),
        ("BISP: apni qist qareebi campsite se hasil karein. Kisi ko koi fee ada na karein.", "8171", "no_red_flags"),
        # "Money received" alerts: real from a short code or name, fake from a 03xx number
        ("You have received Rs. 5,000.00 from ALI KHAN in your JazzCash account. TID: 40123456789", "03001234567", "likely_scam"),
        ("You have received Rs. 5,000.00 from ALI KHAN in your JazzCash account. TID: 40123456789", "8558", "no_red_flags"),
        ("Rs 25,000 has been credited to your HBL account. Ref 99812. Available balance Rs 80,120", "HBL", "no_red_flags"),
        ("Aap ke Easypaisa account mein Rs 3500 jama ho gaye hain. Trx ID 2231", "03451234567", "likely_scam"),
        # "Sent by mistake, please return it"
        ("Assalam o alaikum, ghalti se aap ke number par 2000 rupay bhej diye hain, please wapas kar dein", "03021112223", "likely_scam"),
        ("Bhai maine aap ke account mein 5000 transfer kar diye hain, check kar lo", "03001234567", "no_red_flags"),
        ("Payment received, thanks bhai! Parcel kal bhej dunga", "03001234567", "no_red_flags"),
    ],
)
def test_verdicts(text, sender, verdict):
    assert run(text, sender).verdict == verdict


def test_bisp_message_from_wrong_sender_is_hard_rule():
    result = run("BISP: aap ki qist aa gayi hai, details ke liye rabta karein", sender="03011112222")
    ids = {h.id for h in result.hits}
    assert "bisp_wrong_sender" in ids
    assert result.verdict == "likely_scam"


def test_ai_only_signal_counts_less_and_cannot_be_hard():
    sig = SignalSet()
    sig.add("secret_request", "model: asks for code", "ai")
    sig.add("claims_bank", "HBL", "pattern")
    result = assess(EvalContext(signals=sig))
    hit = next(h for h in result.hits if h.id == "secret_request")
    assert hit.weight == round(RULES["secret_request"].weight * AI_ONLY_FACTOR)
    assert hit.hard is False


def test_safety_notice_is_ignored_when_something_risky_is_present():
    result = run("Do not share your PIN with anyone. Now share the OTP you received to unlock your account")
    assert "safety_notice" not in {h.id for h in result.hits}
    assert result.verdict != "no_red_flags"


def test_lookalike_link_marks_scam():
    link = {
        "url": "http://hbl-verify.xyz", "host": "hbl-verify.xyz", "registered_domain": "hbl-verify.xyz",
        "final_registered_domain": "hbl-verify.xyz", "suffix": "xyz", "risky_tld": True,
        "lookalike_brand": {"key": "hbl", "name": "HBL", "kind": "bank"}, "official_brand": None,
    }
    result = run("HBL: verify your account now at hbl-verify.xyz", links=[link])
    assert result.verdict == "likely_scam"
    rendered = [render_hit(h) for h in result.hits]
    look = next(r for r in rendered if r["id"] == "link_lookalike")
    assert "hbl.com" in look["why"]["en"]
    assert set(look["title"]) == {"en", "ur", "roman"}


def test_every_rule_has_three_languages():
    for rule in RULES.values():
        assert set(rule.title) == {"en", "ur", "roman"}
        assert set(rule.why) == {"en", "ur", "roman"}


def test_challan_from_personal_number_is_suspicious_with_challan_advice():
    from app.guidance.next_steps import next_steps

    text = ("Your Traffic Challan PSID:492618346234112559 is generated using ePay Punjab on 11-Oct-2026 "
            "for payment of Rs.1000 against vehicle number AVE 4551")
    result = run(text, sender="03064709837")
    assert result.verdict == "suspicious"
    assert result.category == "government_notice"
    steps = [s["id"] for s in next_steps(result.verdict, result.category, {"epay_punjab"}, {"challan"})]
    assert "check_challan" in steps and "bisp_official" not in steps


def test_fake_echallan_site_is_a_scam():
    link = {
        "url": "http://psca-echallan.cc", "host": "psca-echallan.cc", "registered_domain": "psca-echallan.cc",
        "final_registered_domain": "psca-echallan.cc", "suffix": "cc", "risky_tld": False,
        "lookalike_brand": {"key": "psca", "name": "Punjab Safe Cities Authority", "kind": "government"},
        "official_brand": None,
    }
    assert run("URGENT: unpaid e-challan. Pay now at psca-echallan.cc", links=[link]).verdict == "likely_scam"


def test_overseas_job_with_passport_gets_beoe_advice():
    from app.guidance.next_steps import next_steps

    text = ("Saudi Arabia mein driver ki job! Free visa aur ticket, 100% genuine, scam nahi. Sirf 35000 processing "
            "fee aur apna passport is number par courier karein 03129876543")
    result = run(text, sender="03129876543")
    ids = {h.id for h in result.hits}
    assert {"job_with_payment", "passport_request", "safety_claim"} <= ids
    assert result.category == "job_task"
    steps = [s["id"] for s in next_steps(result.verdict, result.category, set(), {"overseas_job"})]
    assert "beoe_verify" in steps

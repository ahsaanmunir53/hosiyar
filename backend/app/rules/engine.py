"""Turn rule hits into a score, a verdict and a scam category."""

from dataclasses import dataclass

from app.rules.catalog import RULES, EvalContext, RuleHit, evaluate

SCAM_THRESHOLD = 55
SUSPICIOUS_THRESHOLD = 25

VERDICTS = ("likely_scam", "suspicious", "no_red_flags")

CATEGORY_LABELS = {
    "account_takeover": {"en": "Account takeover", "ur": "اکاؤنٹ پر قبضہ", "roman": "Account par qabza"},
    "government_benefit": {"en": "Fake government payment", "ur": "جعلی سرکاری امداد", "roman": "Jaali sarkari imdad"},
    "government_notice": {"en": "Government notice or fine", "ur": "سرکاری نوٹس یا جرمانہ", "roman": "Sarkari notice ya jurmana"},
    "bank_wallet": {"en": "Bank or wallet impersonation", "ur": "جعلی بینک یا والیٹ", "roman": "Jaali bank ya wallet"},
    "family_emergency": {"en": "Fake family emergency", "ur": "جعلی رشتہ دار ایمرجنسی", "roman": "Jaali rishtedar emergency"},
    "job_task": {"en": "Job or task scam", "ur": "جعلی نوکری", "roman": "Jaali naukri"},
    "investment": {"en": "Investment scam", "ur": "سرمایہ کاری فراڈ", "roman": "Investment fraud"},
    "prize": {"en": "Prize or lottery scam", "ur": "انعام یا لاٹری فراڈ", "roman": "Inaam ya lottery fraud"},
    "delivery": {"en": "Parcel or delivery scam", "ur": "پارسل فراڈ", "roman": "Parcel fraud"},
    "loan": {"en": "Loan scam", "ur": "قرض فراڈ", "roman": "Qarz fraud"},
    "utility": {"en": "Utility bill scam", "ur": "بل فراڈ", "roman": "Bill fraud"},
    "phishing_link": {"en": "Phishing link", "ur": "فشنگ لنک", "roman": "Phishing link"},
    "malicious_file": {"en": "Dangerous file", "ur": "خطرناک فائل", "roman": "Khatarnak file"},
    "other": {"en": "Other", "ur": "دیگر", "roman": "Deegar"},
    "none": {"en": "No scam pattern", "ur": "کوئی فراڈ پیٹرن نہیں", "roman": "Koi fraud pattern nahi"},
}


@dataclass
class Assessment:
    hits: list[RuleHit]
    score: int
    verdict: str
    category: str


def score_hits(hits: list[RuleHit]) -> tuple[int, str]:
    total = sum(h.weight for h in hits)
    score = max(0, min(100, total))
    if any(h.hard for h in hits) or score >= SCAM_THRESHOLD:
        return max(score, SCAM_THRESHOLD if any(h.hard for h in hits) else score), "likely_scam"
    if score >= SUSPICIOUS_THRESHOLD:
        return score, "suspicious"
    return score, "no_red_flags"


def categorize(ctx: EvalContext, hits: list[RuleHit], verdict: str) -> str:
    if verdict == "no_red_flags":
        return "none"
    ids = {h.id for h in hits}
    sig = ctx.signals
    kinds = sig.brand_kinds()
    if "code_hijack" in ids or ("secret_request" in ids and ("whatsapp" in {b.key for b in sig.brands})):
        return "account_takeover"
    if {"fake_credit_alert", "refund_trick"} & ids:
        return "bank_wallet"
    if sig.has("claims_government") or "government" in kinds or "bisp_wrong_sender" in ids:
        # Money promised to you (BISP, relief, refund, prize) versus money demanded from you (fines, challans).
        benefit = (
            any(b.key == "bisp" for b in sig.brands) or sig.has("prize") or sig.has("refund")
            or ("advance_fee" in ids and not sig.has("challan"))
        )
        return "government_benefit" if benefit else "government_notice"
    if "family_emergency" in ids:
        return "family_emergency"
    if {"job_with_payment", "job_offer"} & ids:
        return "job_task"
    if {"too_good", "guaranteed_returns"} & ids:
        return "investment"
    if "loan_with_fee" in ids or (sig.has("loan") and verdict != "no_red_flags"):
        return "loan"
    if "prize" in ids:
        return "prize"
    if "delivery_bait" in ids or ("courier" in kinds and sig.has("delivery")):
        return "delivery"
    if sig.has("utility") or "utility" in kinds:
        return "utility"
    if sig.has("claims_bank") or kinds & {"bank", "wallet"} or "secret_request" in ids:
        return "bank_wallet"
    if any(i.startswith("link_") for i in ids) or "email_brand_mismatch" in ids or "email_freemail_brand" in ids:
        return "phishing_link"
    if {"risky_attachment", "pdf_active_content"} & ids:
        return "malicious_file"
    return "other"


def assess(ctx: EvalContext) -> Assessment:
    hits = evaluate(ctx)
    hits.sort(key=lambda h: (not h.hard, -h.weight))
    score, verdict = score_hits(hits)
    return Assessment(hits=hits, score=score, verdict=verdict, category=categorize(ctx, hits, verdict))


def render_hit(hit: RuleHit) -> dict:
    info = RULES[hit.id]
    params = {k: v for k, v in hit.params.items()}

    def fmt(texts: dict[str, str]) -> dict[str, str]:
        out = {}
        for lang, s in texts.items():
            try:
                out[lang] = s.format(**params)
            except (KeyError, IndexError):
                out[lang] = s
        return out

    return {
        "id": hit.id,
        "weight": hit.weight,
        "hard": hit.hard,
        "title": fmt(info.title),
        "why": fmt(info.why),
        "evidence": hit.evidence,
        "sources": hit.sources,
    }


def rulebook() -> list[dict]:
    return [
        {"id": r.id, "weight": r.weight, "title": r.title, "why": r.why}
        for r in sorted(RULES.values(), key=lambda r: -r.weight)
    ]

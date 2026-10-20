"""Organisations that scammers commonly pretend to be, with their official domains.

Used for two things: noticing which organisation a message claims to come from, and
spotting look-alike links (e.g. hbl-verify.com or jazzcash.com.pk.win-prize.xyz).
Keep this list reviewed; an official domain listed wrongly would hide a real scam.
"""

import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["bank", "wallet", "government", "telecom", "courier", "platform", "utility"]


@dataclass(frozen=True)
class Brand:
    key: str
    name: str
    kind: Kind
    domains: tuple[str, ...]
    aliases: tuple[str, ...]
    # False for brands whose domain label is an ordinary word ("mom", "police", "ica"): only
    # their full names and copies of the official domain inside another host count as look-alikes.
    loose: bool = True


BRANDS: tuple[Brand, ...] = (
    # Banks
    Brand("hbl", "HBL", "bank", ("hbl.com",), ("hbl", "habib bank", "ایچ بی ایل")),
    Brand("ubl", "UBL", "bank", ("ubldigital.com",), ("ubl", "united bank", "یو بی ایل")),
    Brand("mcb", "MCB", "bank", ("mcb.com.pk",), ("mcb", "muslim commercial bank", "ایم سی بی")),
    Brand("meezan", "Meezan Bank", "bank", ("meezanbank.com",), ("meezan", "میزان")),
    Brand("nbp", "National Bank", "bank", ("nbp.com.pk",), ("nbp", "national bank", "نیشنل بینک")),
    Brand("alfalah", "Bank Alfalah", "bank", ("bankalfalah.com",), ("alfalah", "bank alfalah", "الفلاح")),
    Brand("abl", "Allied Bank", "bank", ("abl.com",), ("allied bank", "abl")),
    Brand("faysal", "Faysal Bank", "bank", ("faysalbank.com",), ("faysal bank", "faysal")),
    Brand("bankislami", "BankIslami", "bank", ("bankislami.com.pk",), ("bankislami", "bank islami")),
    # Mobile wallets
    Brand("jazzcash", "JazzCash", "wallet", ("jazzcash.com.pk",), ("jazzcash", "jazz cash", "جاز کیش")),
    Brand("easypaisa", "Easypaisa", "wallet", ("easypaisa.com.pk",), ("easypaisa", "easy paisa", "ایزی پیسہ", "ایزی پیسا")),
    Brand("nayapay", "NayaPay", "wallet", ("nayapay.com",), ("nayapay", "naya pay")),
    Brand("sadapay", "SadaPay", "wallet", ("sadapay.pk",), ("sadapay", "sada pay")),
    # Government
    Brand("bisp", "BISP", "government", ("bisp.gov.pk",), ("bisp", "benazir income support", "benazir kafalat", "benazir", "ehsaas", "ehsas", "بی آئی ایس پی", "بینظیر", "احساس")),
    Brand("nadra", "NADRA", "government", ("nadra.gov.pk",), ("nadra", "نادرا")),
    Brand("fbr", "FBR", "government", ("fbr.gov.pk",), ("fbr", "federal board of revenue", "ایف بی آر")),
    Brand("pta", "PTA", "government", ("pta.gov.pk",), ("pta", "pakistan telecommunication authority", "پی ٹی اے")),
    Brand("sbp", "State Bank of Pakistan", "government", ("sbp.org.pk",), ("state bank", "sbp", "اسٹیٹ بینک", "سٹیٹ بینک")),
    Brand("nccia", "NCCIA", "government", ("nccia.gov.pk",), ("nccia", "cyber crime", "cybercrime")),
    Brand("fia", "FIA", "government", ("fia.gov.pk",), ("fia", "ایف آئی اے")),
    Brand("psca", "Punjab Safe Cities Authority", "government", ("psca.gop.pk",), ("psca", "punjab safe city", "punjab safe cities", "safe city", "safe cities", "سیف سٹی")),
    # A platform-style brand so ordinary words containing "epay"/"punjab" are not flagged as look-alikes.
    Brand("epay_punjab", "ePay Punjab", "platform", ("epay.punjab.gov.pk",), ("epay punjab", "e-pay punjab", "epay", "ای پے پنجاب")),
    Brand("pakpost", "Pakistan Post", "courier", ("pakpost.gov.pk",), ("pakistan post", "pak post", "پاکستان پوسٹ")),
    Brand("beoe", "Bureau of Emigration (BEOE)", "government", ("beoe.gov.pk",), ("beoe", "bureau of emigration", "protector of emigrants", "protector office", "بیورو آف امیگریشن", "پروٹیکٹر")),
    Brand("oec", "Overseas Employment Corporation", "government", ("oec.gov.pk",), ("overseas employment corporation", "oec"), loose=False),
    # Abroad: where many overseas Pakistanis work or apply for visas. Job and visa scams borrow these names.
    Brand("sg_mom", "Ministry of Manpower Singapore", "government", ("mom.gov.sg",), ("ministry of manpower", "mom singapore"), loose=False),
    Brand("sg_ica", "ICA Singapore", "government", ("ica.gov.sg",), ("ica singapore", "immigration & checkpoints", "immigration and checkpoints"), loose=False),
    Brand("sg_police", "Singapore Police Force", "government", ("police.gov.sg",), ("singapore police",), loose=False),
    Brand("sa_absher", "Absher (Saudi Arabia)", "government", ("absher.sa",), ("absher", "ابشر")),
    Brand("ae_icp", "ICP (UAE)", "government", ("icp.gov.ae",), ("icp uae", "federal authority for identity", "uae icp"), loose=False),
    # Couriers and platforms
    Brand("tcs", "TCS", "courier", ("tcsexpress.com",), ("tcs",)),
    Brand("leopards", "Leopards Courier", "courier", ("leopardscourier.com",), ("leopards",)),
    Brand("daraz", "Daraz", "platform", ("daraz.pk",), ("daraz", "دراز")),
    Brand("whatsapp", "WhatsApp", "platform", ("whatsapp.com", "whatsapp.net", "wa.me"), ("whatsapp", "whats app", "واٹس ایپ")),
    Brand("facebook", "Facebook", "platform", ("facebook.com", "fb.com", "fbcdn.net", "messenger.com"), ("facebook",)),
    Brand("google", "Google", "platform", ("google.com", "google.com.pk", "googleusercontent.com", "goo.gl", "youtube.com"), ("google",)),
    # Telecom
    Brand("jazz", "Jazz", "telecom", ("jazz.com.pk",), ("jazz", "mobilink")),
    Brand("zong", "Zong", "telecom", ("zong.com.pk",), ("zong",)),
    Brand("ufone", "Ufone", "telecom", ("ufone.com",), ("ufone",)),
    Brand("telenor", "Telenor", "telecom", ("telenor.com.pk",), ("telenor",)),
    # Utilities
    Brand("lesco", "LESCO", "utility", ("lesco.gov.pk",), ("lesco", "لیسکو")),
    Brand("kelectric", "K-Electric", "utility", ("ke.com.pk",), ("k-electric", "k electric", "kelectric")),
    Brand("sngpl", "SNGPL", "utility", ("sngpl.com.pk",), ("sngpl", "sui gas", "سوئی گیس")),
)

OFFICIAL_DOMAINS: dict[str, Brand] = {d: b for b in BRANDS for d in b.domains}

# Official domains added by an admin at run time (loaded from the database at start-up).
EXTRA_OFFICIAL: dict[str, Brand] = {}


def set_extra_official(rows: list[tuple[str, str, str]]) -> None:
    """Replace the admin-added list with (domain, name, kind) rows."""
    EXTRA_OFFICIAL.clear()
    for domain, name, kind in rows:
        d = domain.lower().strip().removeprefix("www.")
        EXTRA_OFFICIAL[d] = Brand(f"extra:{d}", name, kind if kind in _KINDS else "platform", (d,), ())  # type: ignore[arg-type]


_KINDS = {"bank", "wallet", "government", "telecom", "courier", "platform", "utility"}

# Only government bodies can register these, so any site under them counts as official.
GOVERNMENT_SUFFIXES = ("gov.pk", "gop.pk", "gov.sg", "gov.ae", "gov.sa")

URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "cutt.ly", "t.ly", "is.gd", "rb.gy", "shorturl.at", "tiny.cc",
    "ow.ly", "rebrand.ly", "s.id", "shorte.st", "goo.su", "v.gd", "clck.ru", "t.co", "lnkd.in",
    "bitly.ws", "short.gy", "linktr.ee",
}

# Top-level domains that are cheap to register and heavily abused in SMS phishing.
RISKY_TLDS = {
    "xyz", "top", "click", "live", "buzz", "icu", "shop", "online", "site", "rest", "cyou",
    "monster", "quest", "sbs", "cfd", "lol", "work", "fun", "loan", "win", "bid", "vip", "life",
    "store", "info",
}

_HOMOGLYPHS = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def official_brand_for(registered_domain: str, host: str = "") -> Brand | None:
    """The brand whose official site this is. Matches the registered domain or, for brands whose
    official site is a subdomain (epay.punjab.gov.pk), the host itself."""
    host = host.lower()
    for table in (OFFICIAL_DOMAINS, EXTRA_OFFICIAL):
        for domain, brand in table.items():
            if domain == registered_domain.lower() or host == domain or host.endswith("." + domain):
                return brand
    return None


def is_government_domain(registered_domain: str) -> bool:
    return any(registered_domain.lower().endswith("." + s) for s in GOVERNMENT_SUFFIXES)


# Brand names that are also ordinary words or have many legitimate partner domains.
# For these we only flag exact copies on another domain and typos, not substrings.
_SUBSTRING_KINDS = {"bank", "wallet", "government", "utility", "courier"}


def _typo_limit(length: int) -> int:
    if length >= 8:
        return 2
    if length >= 5:
        return 1
    return 0


def lookalike_brand(host: str, registered_domain: str, domain_label: str) -> Brand | None:
    """Return the brand a non-official host is imitating, if any."""
    if not registered_domain or official_brand_for(registered_domain, host) or is_government_domain(registered_domain):
        return None
    label = domain_label.lower()
    compact = label.replace("-", "")
    folded = compact.translate(_HOMOGLYPHS).replace("rn", "m").replace("vv", "w")
    host_l = host.lower()
    label_tokens = set(re.split(r"[-_]", label))
    sub_tokens = set(re.split(r"[-_.]", host_l[: -len(registered_domain)].strip("."))) - {"", "www"}
    folded_tokens = {tok.translate(_HOMOGLYPHS) for tok in label_tokens}
    for brand in BRANDS:
        names = {brand.key} | {a.replace(" ", "") for a in brand.aliases if a.isascii()}
        # whatsapp-gold.xyz / ubl-online.com / g00gle-security.com: the brand name as a word in another domain.
        if names & (label_tokens | folded_tokens):
            return brand
        for tok in folded_tokens:
            if len(tok) >= 6 and any(len(n) >= 6 and 0 < _levenshtein(tok, n) <= 1 for n in names):
                return brand
        # singapore-police-fine.com / habibbank-online.net: a long full name inside another domain.
        if brand.kind != "platform" and any(len(n) >= 8 and n in compact for n in names if n != brand.key):
            return brand
        # jazzcash.reward-centre.xyz: the brand name as a subdomain of an unrelated site.
        if brand.kind in _SUBSTRING_KINDS and names & sub_tokens:
            return brand
        for official in brand.domains:
            official_label = official.split(".")[0]
            if len(official_label) < 3:
                continue
            # hbl.com.secure-login.xyz: the official domain used as part of another site's name.
            if host_l.startswith(official + ".") or f".{official}." in host_l:
                return brand
            if not brand.loose:
                continue
            # hbl.xyz / jazzcash.online: the brand's exact name on a different domain.
            if compact == official_label or folded == official_label:
                return brand
            if brand.kind in _SUBSTRING_KINDS:
                # jazzcash-reward.xyz / hblverify.com: brand name inside a different domain.
                if len(official_label) >= 4 and official_label in compact:
                    return brand
                if len(official_label) == 3 and (
                    label.startswith(official_label + "-") or label.endswith("-" + official_label)
                    or compact.startswith(official_label + "verify") or compact.startswith(official_label + "online")
                ):
                    return brand
            # easypaissa.com / meezenbank.com / g00gle.com: a letter or two off.
            limit = _typo_limit(len(official_label))
            if limit and (
                0 < _levenshtein(compact, official_label) <= limit
                or 0 < _levenshtein(folded, official_label) <= limit
            ):
                return brand
    return None


def find_claimed_brands(normalized_text: str) -> list[Brand]:
    from app.core.text import URDU_CHAR_MAP

    found: list[Brand] = []
    for brand in BRANDS:
        for alias in brand.aliases:
            alias = alias.translate(URDU_CHAR_MAP)
            if re.search(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", normalized_text):
                if brand not in found:
                    found.append(brand)
                break
    return found

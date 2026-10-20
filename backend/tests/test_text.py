import pytest

from app.core.text import detect_source_language, mixed_script_words, normalize, reply_language_for
from app.core.urls import deobfuscate, extract_urls


def test_lookalike_letters_and_spacing_are_folded():
    assert normalize("Share your НВL O T P") == "share your hbl otp"
    assert normalize("p.i.n") == "pin"
    assert normalize("O​T​P") == "otp"
    assert mixed_script_words("НВL account") == ["НВL"]  # Cyrillic Н and В next to a Latin L
    assert mixed_script_words("Привет, see you") == []  # a whole Russian word is not a trick
    assert mixed_script_words("рassword") == ["рassword"]


@pytest.mark.parametrize(
    ("text", "url"),
    [
        ("visit hbl-verify[.]com now", "http://hbl-verify.com"),
        ("hxxps://jazzcash-kyc[.]top/login", "https://jazzcash-kyc.top/login"),
        ("go to easypaisa-secure dot com", "http://easypaisa-secure.com"),
        ("open bisp(.)gov(.)pk.claim-now.top", "http://bisp.gov.pk.claim-now.top"),
    ],
)
def test_disguised_links_are_found(text, url):
    assert extract_urls(text) == [url]


def test_deobfuscate_keeps_normal_text():
    assert deobfuscate("dot the i") == "dot the i"


@pytest.mark.parametrize(
    ("text", "lang", "reply"),
    [
        ("مبارک شه! تاسو انعام ګټلی دی", "ps", "ur"),
        ("توهان کي انعام مليو آهي، ڪوڊ موڪليو", "sd", "ur"),
        ("تسیں کتھے ہو، ساڈا پیغام پڑھو", "pa", "ur"),
        ("tusi kithe ho, mainu paise bhejo", "pa_roman", "roman"),
        ("Aap ka inaam nikla hai, fee bhejein", "roman", "roman"),
    ],
)
def test_regional_languages(text, lang, reply):
    assert detect_source_language(text) == lang
    assert reply_language_for(lang) == reply

from app.core.redaction import normalize_sender, redact, sender_kind
from app.core.text import detect_language, detect_language_request


def test_redacts_pakistani_numbers_cnic_cards_and_codes():
    r = redact(
        "Call 0300-1234567 or +92 321 7654321. CNIC 35202-1234567-1, card 4111 1111 1111 1111, OTP 482913",
        "s",
    )
    assert "0300" not in r.text and "7654321" not in r.text
    assert "[PHONE_1]" in r.text and "[PHONE_2]" in r.text
    assert "[CNIC_1]" in r.text
    assert "[CARD_1]" in r.text
    assert "[CODE_1]" in r.text
    assert len(r.phone_fingerprints) == 2


def test_number_that_fails_luhn_is_not_called_a_card():
    r = redact("Order number 1234 5678 9012 3456 shipped", "s")
    assert "CARD" not in r.text


def test_urls_survive_but_their_query_strings_are_redacted():
    r = redact("Pay at https://bisp-pay.online/form/2026?id=03001234567&ref=99887766 now", "s")
    assert "https://bisp-pay.online/form/2026?id=[PHONE_1]&ref=[NUMBER]" in r.text
    assert len(r.phone_fingerprints) == 1


def test_emails_and_spaced_numbers_are_redacted():
    r = redact("Mail my.name@gmail.com, IBAN PK36 SCBL 0000 0011 2345 6702, CNIC 35202 1234567 1, "
               "call 0300 123 4567 or 0300-123-4567", "s")
    for secret in ("my.name", "gmail", "SCBL", "35202", "123 4567", "123-4567"):
        assert secret not in r.text
    assert r.counts == {"EMAIL": 1, "IBAN": 1, "CNIC": 1, "PHONE": 2}
    assert len(r.phone_fingerprints) == 1  # the same number written two ways


def test_fingerprint_is_stable_across_formats():
    a = redact("0300-1234567", "s").phone_fingerprints
    b = redact("+923001234567", "s").phone_fingerprints
    assert a == b


def test_sender_kind():
    assert sender_kind("8171") == "shortcode"
    assert sender_kind("0300 1234567") == "mobile"
    assert sender_kind("HBL") == "alphanumeric"
    assert sender_kind(None) == "unknown"
    assert normalize_sender(" 8171 ") == "8171"


def test_language_detection():
    assert detect_language("آپ کا انعام نکلا ہے") == "ur"
    assert detect_language("Mubarak ho aap ka inaam nikla hai, jaldi rabta karein") == "roman"
    assert detect_language("Your parcel is out for delivery") == "en"
    assert detect_language_request("urdu mein batao please") == "ur"
    assert detect_language_request("reply in english") == "en"

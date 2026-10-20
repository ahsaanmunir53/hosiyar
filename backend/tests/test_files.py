import pytest

from app.files import FileUnreadable
from app.files.email_check import read_email
from app.files.pdf import read_pdf
from app.files.qr import crc16_ccitt, describe_qr, parse_payment_qr
from app.files.receipt import consistency_findings
from tests.helpers import GENUINE_EMAIL, PHISHING_EMAIL, make_pdf


def test_pdf_text_links_and_javascript():
    reading = read_pdf(make_pdf("Pay your challan now", link="http://psca-echallan.cc/pay", javascript=True))
    assert "Pay your challan now" in reading.text
    assert "http://psca-echallan.cc/pay" in reading.info["links"]
    assert ("pdf_active_content", "JavaScript") in reading.signals


def test_plain_pdf_has_no_active_content():
    reading = read_pdf(make_pdf("Monthly statement"))
    assert reading.signals == []
    assert reading.info["active_content"] == []


def test_not_a_pdf():
    with pytest.raises(FileUnreadable):
        read_pdf(b"hello, this is not a pdf")


def test_phishing_email_signals():
    reading = read_email(PHISHING_EMAIL)
    names = {n for n, _ in reading.signals}
    assert {"email_auth_failed", "email_brand_mismatch", "email_reply_to_mismatch", "risky_attachment"} <= names
    assert "email_freemail_brand" not in names  # the sender domain is not a free webmail one
    assert ("email_brand_mismatch", "hbl|hbl-secure-verify.top") in reading.signals
    assert reading.info["auth"] == {"spf": "fail", "dkim": "none", "dmarc": "fail"}
    assert "http://hbl-secure-verify.top/login" in reading.text  # hidden behind "www.hbl.com" link text


def test_genuine_email_is_clean():
    reading = read_email(GENUINE_EMAIL)
    assert reading.signals == []
    assert reading.info["from_domain"] == "daraz.pk"


def test_pasted_text_without_headers_is_refused():
    with pytest.raises(FileUnreadable):
        read_email("Dear customer, your account is blocked. Call us now.")


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def test_payment_qr_is_described():
    body = (_tlv("00", "01") + _tlv("01", "12") + _tlv("26", _tlv("00", "PK.RAAST") + _tlv("01", "PK00ABCD1234"))
            + _tlv("52", "5999") + _tlv("53", "586") + _tlv("54", "2500") + _tlv("58", "PK")
            + _tlv("59", "ALI TRADERS") + _tlv("60", "KARACHI") + "6304")
    payload = body + crc16_ccitt(body)
    pay = parse_payment_qr(payload)
    assert pay["merchant_name"] == "ALI TRADERS" and pay["currency"] == "PKR" and pay["checksum_ok"] is True
    assert describe_qr(payload)["content_type"] == "payment"
    assert describe_qr("https://bit.ly/x")["content_type"] == "link"


def test_receipt_consistency_checks():
    ids = [f["id"] for f in consistency_findings({"status_text": "Successful", "amount_text": "Rs. 25,000",
                                                  "date_text": "11-Oct-2026", "transaction_id": "123456789"})]
    assert ids == []
    ids = [f["id"] for f in consistency_findings({"status_text": "Pending", "amount_text": "5,0000", "date_text": "01-Jan-2099"})]
    assert ids == ["status", "no_reference", "amount_format", "future_date"]

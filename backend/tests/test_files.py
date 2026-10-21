from datetime import UTC, datetime

import pytest

from app.files import FileUnreadable
from app.files.email_check import read_email
from app.files.pdf import read_pdf
from app.files.qr import crc16_ccitt, describe_qr, parse_payment_qr
from app.files.receipt import assessment, consistency_findings
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


NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)  # 2 pm in Pakistan


def test_receipt_consistency_checks():
    ids = [f["id"] for f in consistency_findings({"status_text": "Successful", "amount_text": "Rs. 25,000",
                                                  "date_text": "21-Oct-2026", "transaction_id": "123456789",
                                                  "receiver_account_masked": "0305****284"}, NOW)]
    assert ids == []
    ids = [f["id"] for f in consistency_findings({"status_text": "Pending", "amount_text": "5,0000", "date_text": "01-Jan-2099"}, NOW)]
    assert ids == ["status", "no_reference", "amount_format", "future_date"]


def test_fake_receipt_with_old_date_and_wrong_mask_length_is_flagged():
    # Fields as read from a made-up JazzCash receipt: two years old, 13-character masked numbers.
    fields = {"app_name": "JazzCash", "status_text": "Transaction Successful", "amount_text": "Rs. 2,350.00",
              "date_text": "29 Oct 2024, 03:24 PM", "transaction_id": "069108762934",
              "receiver_account_masked": "0305******284", "sender_account_masked": "0312******567"}
    found = consistency_findings(fields, NOW)
    assert {f["id"] for f in found} == {"old_date", "number_length"}
    assert next(f for f in found if f["id"] == "old_date")["severity"] == "high"
    assert assessment(found) == "likely_fake"


def test_fake_receipt_with_placeholder_numbers_is_flagged():
    fields = {"status_text": "Transaction Successful", "amount_text": "Rs. 2,750.00", "transaction_id": "031547892736",
              "date_text": "October 28, 2024", "time_text": "04:17 PM", "status_bar_time": "3:24",
              "receiver_account_masked": "03011234567", "sender_account_masked": "03098765432"}
    ids = [f["id"] for f in consistency_findings(fields, NOW)]
    assert ids.count("placeholder_number") == 2 and "old_date" in ids
    assert "clock_before_payment" not in ids  # the screenshot may be from another day, so no clock check


def test_status_bar_clock_earlier_than_a_payment_made_today():
    base = {"status_text": "Successful", "amount_text": "Rs. 5,000", "transaction_id": "40123456789",
            "date_text": "21 Oct 2026", "receiver_account_masked": "0300****123"}
    early = consistency_findings({**base, "time_text": "04:17 PM", "status_bar_time": "3:24"}, NOW)
    assert "clock_before_payment" in {f["id"] for f in early}
    fine = consistency_findings({**base, "time_text": "11:05 AM", "status_bar_time": "3:24"}, NOW)  # 3:24 pm is later
    assert "clock_before_payment" not in {f["id"] for f in fine}
    assert assessment(fine) == "no_signs"


def test_a_few_days_old_receipt_is_only_a_caution():
    found = consistency_findings({"status_text": "Successful", "transaction_id": "1", "date_text": "16-Oct-2026"}, NOW)
    assert [(f["id"], f["severity"]) for f in found] == [("old_date", "medium")]
    assert assessment(found) == "suspicious"

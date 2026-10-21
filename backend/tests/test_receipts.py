"""Fake payment receipts: text checks, image-file checks, receipt memory and the API."""

import io
import struct
import zlib
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.redaction import phone_fingerprint
from app.db.models import WatchlistEntry
from app.db.session import init_db, make_engine, make_sessionmaker
from app.files.image_meta import inspect
from app.files.receipt import (
    assessment,
    consistency_findings,
    history_findings,
    image_findings,
    number_findings,
    words_to_number,
)

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
BASE = {"status_text": "Transaction Successful", "transaction_id": "40123456789", "date_text": "21 Oct 2026",
        "amount_text": "Rs. 2,350.00", "receiver_account_masked": "0305****284"}


def ids(fields, **kw):
    return [f["id"] for f in consistency_findings({**BASE, **fields}, NOW, **kw)]


# --------------------------------------------------------------------------- text on the receipt

def test_a_clean_receipt_has_no_findings():
    assert ids({}) == []


@pytest.mark.parametrize(("fields", "expected"), [
    ({"date_text": "31 Feb 2026"}, "impossible_date"),
    ({"date_text": "30/02/2026"}, "impossible_date"),
    ({"date_text": "Wed, 29 Oct 2024"}, "wrong_weekday"),
    ({"date_text": "21 Oct 2026", "time_text": "14:30 PM"}, "impossible_time"),
    ({"time_text": "10:75 AM"}, "impossible_time"),
    ({"fee_text": "Rs. 0.00", "total_text": "Rs. 3,350.00"}, "total_mismatch"),
    ({"amount_in_words": "Two Thousand Eight Hundred Fifty Rupees Only"}, "words_mismatch"),
    ({"receiver_account_masked": "PK36SCBL0000001123456703"}, "iban_checksum"),
    ({"receiver_account_masked": "PK36SCBL00000011234567"}, "iban_length"),
    ({"app_name": "JazCash"}, "brand_spelling"),
    ({"app_name": "Easypasia"}, "brand_spelling"),
])
def test_receipt_mistakes_are_found(fields, expected):
    found = ids(fields)
    assert expected in found


@pytest.mark.parametrize("fields", [
    {"date_text": "Tue, 29 Oct 2026"},  # wrong weekday only if the date is real: 29 Oct 2026 is a Thursday
    {"date_text": "10/21/2026"},  # month-first dates are read both ways
    {"fee_text": "Rs. 15", "total_text": "Rs. 2,365.00"},
    {"total_text": "Rs. 2,350"},
    {"amount_in_words": "Two Thousand Three Hundred Fifty Rupees Only"},
    {"amount_in_words": "Rupees two thousand three hundred and fifty and fifty paisa only"},
    {"receiver_account_masked": "PK36SCBL0000001123456702"},
    {"receiver_account_masked": "PK36SCBL0000****23456702"},
    {"app_name": "JazzCash"},
    {"app_name": "Jazz Cash"},
    {"app_name": "HBL Mobile"},
    {"app_name": "Meezan Bank"},
])
def test_genuine_details_are_not_flagged(fields):
    found = ids(fields)
    assert not {"impossible_date", "total_mismatch", "words_mismatch", "iban_checksum", "iban_length",
                "brand_spelling", "impossible_time"} & set(found)


def test_weekday_check():
    assert "wrong_weekday" not in ids({"date_text": "Tue, 29 Oct 2024"})  # it was a Tuesday
    assert "wrong_weekday" in ids({"date_text": "Tue, 29 Oct 2026"})


def test_words_to_number():
    assert words_to_number("Two Thousand Three Hundred Fifty Rupees Only") == 2350
    assert words_to_number("Rupees One Lakh Twenty-Five Thousand only") == 125000
    assert words_to_number("Two crore") == 20_000_000
    assert words_to_number("Rs 2,350") is None
    assert words_to_number("two thousand and fifty paisa") is None


def test_what_the_person_expected():
    assert "overpaid" in ids({}, expected_amount="2000")
    assert "underpaid" in ids({}, expected_amount="3,000")
    assert not {"overpaid", "underpaid"} & set(ids({}, expected_amount="Rs 2,350"))
    assert not {"overpaid", "underpaid"} & set(ids({"amount_text": "Rs. 2,500"}, expected_amount="2.5k"))
    assert "not_your_account" not in ids({}, my_account="0305 1234284")
    assert "not_your_account" not in ids({}, my_account="4284")  # last digits are enough
    assert "not_your_account" in ids({}, my_account="03001112223")
    assert "not_your_account" in ids({}, my_account="1111")
    # A phone number cannot be compared with an IBAN
    assert "not_your_account" not in ids({"receiver_account_masked": "PK36SCBL0000001123456702"}, my_account="03001112223")


def test_ai_observations_alone_never_make_a_receipt_fake():
    fields = {**BASE, "visual_issues": ["digits use two fonts", "logo looks blurry"]}
    found = consistency_findings(fields, NOW)
    assert assessment(found) == "suspicious"
    assert assessment(consistency_findings({**BASE, "visual_issues": ["logo looks blurry"]}, NOW)) == "no_signs"


# --------------------------------------------------------------------------- the image file

def _png(width: int, height: int, texts: dict[bytes, bytes] | None = None, itxt: bytes | None = None) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    for key, value in (texts or {}).items():
        out += chunk(b"tEXt", key + b"\0" + value)
    if itxt:
        out += chunk(b"iTXt", b"XML:com.adobe.xmp\0\x01\x00\0\0" + zlib.compress(itxt))
    return out + chunk(b"IDAT", zlib.compress(b"\0" * 10)) + chunk(b"IEND", b"")


def _jpeg(width: int, height: int, app1: bytes) -> bytes:
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    app = b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
    return b"\xff\xd8" + app + sof + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + b"\x00" * 20 + b"\xff\xd9"


def _webp(width: int, height: int) -> bytes:
    body = b"\x00\x00\x00\x00" + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    chunk = b"VP8X" + struct.pack("<I", len(body)) + body
    return b"RIFF" + struct.pack("<I", 4 + len(chunk)) + b"WEBP" + chunk


def test_image_size_and_editor_are_read_from_metadata_only():
    meta = inspect(_png(1080, 2400, {b"Software": b"Adobe Photoshop 25.0 (Windows)"}))
    assert (meta["width"], meta["height"]) == (1080, 2400)
    assert meta["editors"] == ["Adobe Photoshop"] and meta["ai"] == []
    assert [f["id"] for f in image_findings(meta)] == ["edited_image"]


def test_ai_generator_labels_are_found():
    xmp = b'<x:xmpmeta><Iptc4xmpExt:DigitalSourceType>http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia</Iptc4xmpExt:DigitalSourceType></x:xmpmeta>'
    meta = inspect(_png(1024, 1536, itxt=xmp))
    assert meta["ai"]
    found = image_findings(meta)
    assert [f["id"] for f in found] == ["ai_generated"] and assessment(found) == "likely_fake"
    sd = inspect(_png(832, 1216, {b"parameters": b"a receipt\nSteps: 30, Sampler: Euler a, CFG scale: 7"}))
    assert sd["ai"]


def test_ai_size_alone_is_only_a_caution():
    found = image_findings(inspect(_png(1024, 1536)))
    assert [(f["id"], f["severity"]) for f in found] == [("ai_size", "medium")]


def test_jpeg_and_webp():
    meta = inspect(_jpeg(1170, 2532, b"Exif\x00\x00 ... Software\x00PicsArt Photo Studio"))
    assert (meta["width"], meta["height"]) == (1170, 2532) and meta["editors"] == ["PicsArt"]
    assert inspect(_webp(1024, 1024))["width"] == 1024
    assert inspect(b"not an image") == {"width": None, "height": None, "ai": [], "editors": [], "c2pa": False}


def test_words_inside_other_words_do_not_count():
    assert inspect(_png(1080, 2400, {b"Comment": b"canvas rendering"}))["editors"] == []


# --------------------------------------------------------------------------- memory and reported numbers

@pytest.fixture
async def deps(settings):
    engine = make_engine(settings)
    await init_db(engine)
    yield SimpleNamespace(settings=settings, sessionmaker=make_sessionmaker(engine), http=None)
    await engine.dispose()


async def test_the_same_receipt_from_another_person_is_noticed(deps):
    fields = {"transaction_id": "TID 0691-0876-2934", "amount_text": "Rs. 2,350.00"}
    assert await history_findings(deps, fields, "user-a", False) == []
    assert await history_findings(deps, fields, "user-a", False) == []  # the same person checking again
    again = await history_findings(deps, {"transaction_id": "069108762934", "amount_text": "2350"}, "user-b", False)
    assert [f["id"] for f in again] == ["seen_before"]
    other_amount = await history_findings(deps, {**fields, "amount_text": "Rs. 9,000"}, "user-b", False)
    assert other_amount == []


async def test_a_receipt_found_fake_warns_the_next_person(deps):
    fields = {"transaction_id": "031547892736", "amount_text": "Rs. 2,750.00"}
    await history_findings(deps, fields, "user-a", True)
    found = await history_findings(deps, fields, "user-b", False)
    assert [(f["id"], f["severity"]) for f in found] == [("seen_fake", "high")]


async def test_a_confirmed_scam_number_on_the_receipt(deps):
    async with deps.sessionmaker() as session:
        session.add(WatchlistEntry(kind="phone_fp", value=phone_fingerprint("03011234567", deps.settings.fingerprint_secret),
                                   label="0301-***-4567", added_by="test"))
        await session.commit()
    found = await number_findings(deps, {"receiver_account_masked": "0301 1234567", "sender_account_masked": "0312******567"})
    assert [f["id"] for f in found] == ["reported_number"]
    assert await number_findings(deps, {"receiver_account_masked": "03009998887"}) == []


# --------------------------------------------------------------------------- API

def test_api_runs_the_image_checks_even_without_a_gemini_key(client):
    xmp = b"<rdf:Description>trainedAlgorithmicMedia</rdf:Description>"
    r = client.post("/api/receipt", files={"file": ("pay.png", io.BytesIO(_png(1024, 1536, itxt=xmp)), "image/png")},
                    data={"expected_amount": "2000", "my_account": "1234", "client_id": "abcd1234-test"})
    assert r.status_code == 200
    body = r.json()
    assert body["assessment"] == "likely_fake"
    assert [f["id"] for f in body["findings"]] == ["ai_generated"]
    assert "GOOGLE_API_KEY" in body["unavailable"]
    assert body["image"] == {"width": 1024, "height": 1536}

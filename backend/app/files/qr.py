"""QR codes are decoded in the browser (nothing but the decoded text is uploaded).

Payment QR codes (EMVCo format, used by Raast and most wallets) start with "000201".
Scanning one *pays* the merchant named in it, which is the opposite of what "scan to
receive money" messages claim, so the result shows who would be paid.
"""

CURRENCIES = {"586": "PKR", "840": "USD", "784": "AED", "682": "SAR", "702": "SGD", "826": "GBP", "978": "EUR"}


def parse_tlv(payload: str) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    while i + 4 <= len(payload):
        tag, length = payload[i:i + 2], payload[i + 2:i + 4]
        if not (tag.isdigit() and length.isdigit()):
            break
        n = int(length)
        out[tag] = payload[i + 4:i + 4 + n]
        i += 4 + n
    return out


def crc16_ccitt(data: str) -> str:
    crc = 0xFFFF
    for byte in data.encode():
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def parse_payment_qr(payload: str) -> dict | None:
    payload = payload.strip()
    if not payload.startswith("000201"):
        return None
    fields = parse_tlv(payload)
    if "59" not in fields and "26" not in fields and not any(f"{n:02d}" in fields for n in range(26, 52)):
        return None
    crc_ok = None
    if "63" in fields and payload[-8:-4] == "6304":
        crc_ok = crc16_ccitt(payload[:-4]) == payload[-4:].upper()
    return {
        "merchant_name": fields.get("59"),
        "city": fields.get("60"),
        "country": fields.get("58"),
        "amount": fields.get("54"),
        "currency": CURRENCIES.get(fields.get("53", ""), fields.get("53")),
        "dynamic": fields.get("01") == "12",
        "checksum_ok": crc_ok,
    }


def describe_qr(payload: str) -> dict:
    payment = parse_payment_qr(payload)
    lowered = payload.strip().lower()
    if payment:
        kind = "payment"
    elif lowered.startswith(("http://", "https://", "www.")):
        kind = "link"
    elif lowered.startswith(("upi:", "bitcoin:", "ethereum:", "tron:")):
        kind = "crypto_or_payment"
    elif lowered.startswith(("wifi:", "tel:", "smsto:", "mailto:", "begin:vcard")):
        kind = lowered.split(":", 1)[0]
    else:
        kind = "text"
    return {"kind": "qr", "content_type": kind, "payment": payment}

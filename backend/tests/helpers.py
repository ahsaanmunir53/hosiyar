"""Small builders for test files."""


def make_pdf(text: str, link: str | None = None, javascript: bool = False) -> bytes:
    """A minimal one-page PDF with a line of text, optionally a link annotation and an open action."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    catalog = "<< /Type /Catalog /Pages 2 0 R" + (" /OpenAction 7 0 R" if javascript else "") + " >>"
    annots = " /Annots [6 0 R]" if link else ""
    bodies: list[bytes] = [
        catalog.encode(),
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
         f"/Resources << /Font << /F1 5 0 R >> >>{annots} >>").encode(),
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Type /Annot /Subtype /Link /Rect [72 700 300 730] /A << /S /URI /URI ({link or ''}) >> >>".encode(),
        b"<< /S /JavaScript /JS (app.alert\\('hello'\\);) >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(bodies, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(bodies) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


PHISHING_EMAIL = """From: "HBL Alerts" <alerts@hbl-secure-verify.top>
Reply-To: help.desk@gmail.com
To: you@example.com
Subject: Your HBL account will be suspended
Authentication-Results: mx.google.com; spf=fail smtp.mailfrom=hbl-secure-verify.top; dkim=none; dmarc=fail header.from=hbl-secure-verify.top
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="b1"

--b1
Content-Type: text/html; charset=utf-8

<p>Dear customer, your account will be blocked. Verify within 24 hours at
<a href="http://hbl-secure-verify.top/login">www.hbl.com</a>.</p>
--b1
Content-Type: text/html; name="statement.html"
Content-Disposition: attachment; filename="statement.html"

<html>fake login</html>
--b1--
"""

GENUINE_EMAIL = """From: Daraz <noreply@daraz.pk>
To: you@example.com
Subject: Your order has shipped
Authentication-Results: mx.google.com; spf=pass smtp.mailfrom=daraz.pk; dkim=pass; dmarc=pass header.from=daraz.pk
Content-Type: text/plain; charset=utf-8

Hi, your order 1234 has shipped and will arrive on Friday. You can track it in the Daraz app.
"""

"""Readers for files people upload: PDFs and emails (.eml or pasted source).

Each reader returns the text to analyse plus deterministic signals about the file itself
(scripts inside a PDF, an email that failed sender checks, risky attachments)."""

from dataclasses import dataclass, field


class FileUnreadable(ValueError):
    """The file could not be read (damaged, password-protected, empty)."""


@dataclass
class FileReading:
    text: str
    signals: list[tuple[str, str]] = field(default_factory=list)  # (signal name, evidence)
    info: dict = field(default_factory=dict)  # shown to the user in the result


# Extensions that run code or open a fake page when clicked. Archives are left out: they are
# common in normal mail, and what is inside them is not inspected.
RISKY_EXTENSIONS = {
    "apk", "exe", "scr", "bat", "cmd", "com", "js", "jse", "vbs", "vbe", "wsf", "hta", "msi", "jar",
    "ps1", "lnk", "iso", "img", "html", "htm", "shtml", "xhtml", "svg", "docm", "xlsm", "pptm", "dotm",
}


def risky_names(names: list[str]) -> list[str]:
    out = []
    for name in names:
        ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
        if ext in RISKY_EXTENSIONS:
            out.append(name[:80])
    return out


def sanitize_info(info: dict, secret: str) -> dict:
    """What is shown and kept about a file: personal details removed from names and subjects,
    and query strings dropped from links."""
    from app.core.redaction import redact
    from app.intel.indicators import clean_url

    out = dict(info)
    for key in ("subject", "from_name"):
        if isinstance(out.get(key), str):
            out[key] = redact(out[key], secret).text
    if isinstance(out.get("attachments"), list):
        out["attachments"] = [redact(str(a), secret).text for a in out["attachments"]]
    if isinstance(out.get("links"), list):
        out["links"] = [u for u in (clean_url(str(x)) for x in out["links"]) if u]
    return out

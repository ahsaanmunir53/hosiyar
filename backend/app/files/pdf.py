"""Read a PDF: its text, the links in it (including clickable link annotations) and any
active content (JavaScript, auto-run actions, embedded files)."""

import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.files import FileReading, FileUnreadable, risky_names

log = logging.getLogger(__name__)


def _resolve(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


def _action_kinds(action) -> set[str]:
    action = _resolve(action)
    kinds: set[str] = set()
    if hasattr(action, "get"):
        kind = str(action.get("/S", ""))
        if kind == "/JavaScript":
            kinds.add("JavaScript")
        elif kind == "/Launch":
            kinds.add("launches a program")
        elif kind == "/SubmitForm":
            kinds.add("sends a form")
    return kinds


def read_pdf(data: bytes, max_pages: int = 10) -> FileReading:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise FileUnreadable("This PDF is password-protected, so it cannot be read.") from exc
        pages = list(reader.pages)[:max_pages]
    except FileUnreadable:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise FileUnreadable("This file does not look like a readable PDF.") from exc

    texts: list[str] = []
    links: list[str] = []
    active: set[str] = set()
    for page in pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception as exc:  # malformed content streams should not stop the check
            log.info("pdf text extraction failed on a page: %s", type(exc).__name__)
        for annot in _resolve(page.get("/Annots")) or []:
            annot = _resolve(annot)
            action = annot.get("/A") if hasattr(annot, "get") else None
            if action is not None:
                action = _resolve(action)
                uri = action.get("/URI") if hasattr(action, "get") else None
                if uri:
                    links.append(str(uri)[:500])
                active |= _action_kinds(action)
        if "/AA" in page:
            active.add("runs actions when a page opens")

    root = _resolve(reader.trailer.get("/Root")) or {}
    if "/OpenAction" in root:
        kinds = _action_kinds(root["/OpenAction"])
        active |= kinds
    if "/AA" in root:
        active.add("runs actions when opened")
    names = _resolve(root.get("/Names")) or {}
    if hasattr(names, "get") and "/JavaScript" in names:
        active.add("JavaScript")
    attachments: list[str] = []
    try:
        attachments = list(reader.attachments.keys())
    except Exception:
        attachments = []
    if attachments:
        active.add("embedded files")
    if "/AcroForm" in root and _resolve(root["/AcroForm"]).get("/XFA") is not None:
        active.add("XFA form")

    text = "\n".join(t.strip() for t in texts if t.strip())
    unique_links = list(dict.fromkeys(links))[:20]
    if unique_links:
        text += "\n\nLinks in the file: " + " ".join(unique_links)
    if not text.strip() and not active:
        raise FileUnreadable("No text was found in this PDF. If it is a scanned image, upload a screenshot instead.")

    signals: list[tuple[str, str]] = []
    if active:
        for what in sorted(active):
            signals.append(("pdf_active_content", what))
    risky = risky_names(attachments)
    for name in risky:
        signals.append(("risky_attachment", name))
    info = {
        "kind": "pdf",
        "pages": len(reader.pages),
        "pages_read": len(pages),
        "links": unique_links,
        "active_content": sorted(active),
        "attachments": attachments[:20],
    }
    return FileReading(text=text, signals=signals, info=info)

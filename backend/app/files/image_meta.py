"""What an image file says about itself: its size and the software that made or edited it.

Only the metadata parts of the file are read (PNG text chunks, JPEG APP segments, WebP EXIF/XMP),
never the pixels, so random bytes in the picture cannot look like a marker. No extra library is needed.

* AI generators often label their output: C2PA "content credentials" (ChatGPT/DALL-E, Adobe Firefly,
  Google), the IPTC source type "trainedAlgorithmicMedia", or Stable Diffusion's "parameters" text.
* Editing apps (Photoshop, PicsArt, Canva, Snapseed...) usually write their name into the file.
* AI generators produce a few fixed sizes (1024x1536 and so on); phone screenshots have the
  phone's screen size.

Messaging apps such as WhatsApp strip metadata, so a clean result proves nothing.
"""

import re
import struct
import zlib

AI_MARKERS = {
    "trainedalgorithmicmedia": "an AI image generator (IPTC source type)",
    "openai": "OpenAI (ChatGPT / DALL-E)",
    "chatgpt": "ChatGPT",
    "dall-e": "DALL-E",
    "dall·e": "DALL-E",
    "gpt-4o": "ChatGPT (GPT-4o)",
    "gpt-image": "ChatGPT (GPT Image)",
    "midjourney": "Midjourney",
    "stable diffusion": "Stable Diffusion",
    "stablediffusion": "Stable Diffusion",
    "comfyui": "ComfyUI (Stable Diffusion)",
    "adobe firefly": "Adobe Firefly",
    "made with google ai": "Google AI (Gemini / Imagen)",
    "google imagen": "Google Imagen",
    "ideogram": "Ideogram",
    "leonardo.ai": "Leonardo AI",
    "nano banana": "Gemini image generation",
}
EDITOR_MARKERS = {
    "photoshop": "Adobe Photoshop",
    "lightroom": "Adobe Lightroom",
    "picsart": "PicsArt",
    "canva": "Canva",
    "snapseed": "Snapseed",
    "gimp": "GIMP",
    "pixlr": "Pixlr",
    "photopea": "Photopea",
    "polarr": "Polarr",
    "meitu": "Meitu",
    "facetune": "Facetune",
    "photoroom": "PhotoRoom",
    "fotor": "Fotor",
    "inshot": "InShot",
    "remini": "Remini",
}
# Sizes AI image tools produce by default (width, height). Phone screenshots look like 1080x2400.
AI_SIZES = {
    (1024, 1024), (1024, 1536), (1536, 1024), (1024, 1792), (1792, 1024), (2048, 2048),
    (896, 1152), (1152, 896), (832, 1216), (1216, 832), (768, 1344), (1344, 768),
    (832, 1248), (1248, 832), (864, 1184), (1184, 864), (896, 1280), (1280, 896),
    (768, 1408), (1408, 768), (1536, 672), (672, 1536), (512, 512), (768, 768),
}


def _png(data: bytes) -> tuple[tuple[int, int] | None, list[bytes], bool]:
    size, texts, c2pa = None, [], False
    pos = 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR" and len(body) >= 8:
            size = struct.unpack(">II", body[:8])
        elif kind in (b"tEXt", b"iTXt", b"eXIf"):
            texts.append(body)
            if kind == b"iTXt" and len(body) > 2:
                # keyword\0 compression-flag method lang\0 translated\0 text
                parts = body.split(b"\0", 1)
                if len(parts) == 2 and parts[1][:1] == b"\x01":
                    try:
                        texts.append(zlib.decompress(parts[1].split(b"\0", 3)[-1][:2_000_000]))
                    except (zlib.error, IndexError):
                        pass
        elif kind == b"zTXt":
            key, _, rest = body.partition(b"\0")
            texts.append(key)
            try:
                texts.append(zlib.decompress(rest[1:][:2_000_000]))
            except zlib.error:
                pass
        elif kind == b"caBX":
            c2pa = True
            texts.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + length
    return size, texts, c2pa


def _jpeg(data: bytes) -> tuple[tuple[int, int] | None, list[bytes], bool]:
    size, texts, c2pa = None, [], False
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        body = data[pos + 4:pos + 2 + length]
        if 0xE0 <= marker <= 0xEF or marker == 0xFE:
            texts.append(body)
            if marker == 0xEB and (b"c2pa" in body or b"jumb" in body):
                c2pa = True
        elif marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF) and len(body) >= 5:
            height, width = struct.unpack(">HH", body[1:5])
            size = (width, height)
        elif marker == 0xDA:  # start of the picture data: no metadata after this point
            break
        pos += 2 + length
    return size, texts, c2pa


def _webp(data: bytes) -> tuple[tuple[int, int] | None, list[bytes], bool]:
    size, texts, c2pa = None, [], False
    pos = 12
    while pos + 8 <= len(data):
        kind, length = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + length]
        if kind == b"VP8X" and len(body) >= 10:
            size = (1 + int.from_bytes(body[4:7], "little"), 1 + int.from_bytes(body[7:10], "little"))
        elif kind == b"VP8 " and len(body) >= 10 and size is None:
            size = (struct.unpack("<H", body[6:8])[0] & 0x3FFF, struct.unpack("<H", body[8:10])[0] & 0x3FFF)
        elif kind == b"VP8L" and len(body) >= 5 and size is None:
            bits = int.from_bytes(body[1:5], "little")
            size = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        elif kind in (b"EXIF", b"XMP "):
            texts.append(body)
        elif kind == b"C2PA":
            c2pa = True
            texts.append(body)
        pos += 8 + length + (length & 1)
    return size, texts, c2pa


def inspect(data: bytes) -> dict:
    """{'width', 'height', 'ai': [names], 'editors': [names], 'c2pa': bool}. Unknown formats give empty results."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        size, texts, c2pa = _png(data)
    elif data[:3] == b"\xff\xd8\xff":
        size, texts, c2pa = _jpeg(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        size, texts, c2pa = _webp(data)
    else:
        size, texts, c2pa = None, [], False
    blob = b" ".join(texts).lower()
    text = blob.decode("latin-1")
    ai = sorted({name for marker, name in AI_MARKERS.items() if marker in text})
    if re.search(r"(?:^|\W)parameters\W", text) and re.search(r"steps:\s*\d+.*sampler:", text, re.S):
        ai.append("Stable Diffusion (generation settings)")
    editors = sorted({name for marker, name in EDITOR_MARKERS.items()
                      if re.search(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", text)})
    width, height = size if size else (None, None)
    return {"width": width, "height": height, "ai": ai, "editors": editors, "c2pa": c2pa}

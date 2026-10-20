"""Reading screenshots (Gemini vision) and voice notes (Groq Whisper)."""

import base64

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import gemini_chat, text_of
from app.config import Settings


class MediaUnavailable(RuntimeError):
    """Raised when the needed API key is not configured."""


OCR_PROMPT = (
    "Transcribe every piece of text visible in this screenshot of a message, exactly as written, "
    "keeping the original language and script (English, Urdu or Roman Urdu). Include the sender name "
    "or number if visible. Output only the transcribed text, nothing else."
)


async def image_to_text(settings: Settings, data: bytes, mime: str) -> str:
    if not settings.google_api_key:
        raise MediaUnavailable("Reading screenshots needs GOOGLE_API_KEY (Gemini).")
    model = gemini_chat(settings, settings.gemini_vision_model, retries=1)
    b64 = base64.b64encode(data).decode()
    msg = HumanMessage(
        content=[
            {"type": "text", "text": OCR_PROMPT},
            {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"},
        ]
    )
    result = await model.ainvoke([SystemMessage("You are an exact OCR engine."), msg])
    return text_of(result).strip()


async def audio_to_text(settings: Settings, data: bytes, filename: str) -> str:
    if not settings.groq_api_key:
        raise MediaUnavailable("Reading voice notes needs GROQ_API_KEY (Whisper on Groq).")
    from groq import AsyncGroq

    client = AsyncGroq(api_key=settings.groq_api_key, timeout=settings.llm_timeout_seconds)
    result = await client.audio.transcriptions.create(
        model=settings.groq_whisper_model,
        file=(filename, data),
        response_format="json",
        temperature=0,
    )
    return (getattr(result, "text", "") or "").strip()

"""Request and response models (the API contract the frontend relies on)."""

from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["en", "ur", "roman"]


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    sender: str | None = Field(default=None, max_length=64, description="Who sent it, e.g. 8171, HBL or 0300...")
    share: bool = Field(default=False, description="Share the redacted message as a report (reviewed before it joins the memory)")
    language: Lang | None = None
    client_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{8,64}$", description="Random id kept by the browser")
    source_kind: Literal["text", "qr"] = "text"
    captcha_token: str | None = Field(default=None, max_length=2048)


class EmailRequest(BaseModel):
    raw: str = Field(min_length=20, max_length=600_000, description="The email's full source (headers and body)")
    share: bool = False
    language: Lang | None = None
    client_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{8,64}$")
    captcha_token: str | None = Field(default=None, max_length=2048)


class LookupRequest(BaseModel):
    value: str = Field(min_length=3, max_length=500)
    kind: Literal["auto", "phone", "link", "account"] = "auto"
    captcha_token: str | None = Field(default=None, max_length=2048)


class FollowupRequest(BaseModel):
    thread_id: str = Field(min_length=8, max_length=64)
    question: str = Field(min_length=1, max_length=500)
    language: Lang | None = None
    client_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{8,64}$")


class I18n(BaseModel):
    en: str
    ur: str
    roman: str


class Reason(BaseModel):
    id: str
    weight: int
    hard: bool
    title: I18n
    why: I18n
    evidence: list[str]
    sources: list[str]


class Step(BaseModel):
    id: str
    text: I18n
    urgent: bool = False
    link: str | None = None


class Category(BaseModel):
    id: str
    label: I18n


class Explanation(BaseModel):
    language: Lang
    text: str
    source: Literal["ai", "template"]
    templates: I18n


class AnalysisResponse(BaseModel):
    id: str
    thread_id: str
    verdict: Literal["likely_scam", "suspicious", "no_red_flags"]
    score: int
    category: Category
    language: Lang
    explanation: Explanation
    reasons: list[Reason]
    links: list[dict]
    similar: list[dict]
    reported_number_count: int
    next_steps: list[Step]
    investigation: list[dict]
    redactions: dict[str, int]
    analyzed_text: str
    source_kind: Literal["text", "image", "audio", "qr", "pdf", "email"]
    source_language: str
    file_info: dict | None = None
    reported_account_count: int = 0
    watchlist: list[dict] = []
    report_status: Literal["approved", "pending"] | None = None
    ai_summary: str | None
    model: str
    rules_version: str
    degraded: list[str]
    shared: bool


class FollowupAnswer(BaseModel):
    question: str
    answer: str
    language: Lang
    source: Literal["ai", "template"]


class FollowupResponse(BaseModel):
    thread_id: str
    answer: FollowupAnswer

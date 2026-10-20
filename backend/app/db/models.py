"""Database tables.

* analyses       one row per check: rule ids and metadata, never the raw message
* reports        messages people chose to share (redacted), waiting for or past review
* indicators     domains, URLs and phone/account fingerprints taken from shared reports
* campaigns      groups of reports that share an indicator or read alike
* watchlist      indicators an analyst confirmed; a match is a decisive rule
* official_domains_extra   official sites added by an admin (the built-in list is in code)
* ai_cache       model readings of a redacted text, so a repeated scam costs no quota
* rule_suggestions   regex ideas from the rule-suggestion agent, never applied automatically
* family_links   Telegram family alerts
* alert_log      weekly warnings and family alerts that were sent
* users          analysts and admins for the review panel
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    channel: Mapped[str] = mapped_column(String(16), default="web")
    user_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verdict: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8))
    rule_ids: Mapped[list] = mapped_column(JSON, default=list)
    hard_rule_ids: Mapped[list] = mapped_column(JSON, default=list)
    brands: Mapped[list] = mapped_column(JSON, default=list)
    link_domains: Mapped[list] = mapped_column(JSON, default=list)
    memory_matches: Mapped[int] = mapped_column(Integer, default=0)
    llm_model: Mapped[str] = mapped_column(String(64), default="none")
    rules_version: Mapped[str] = mapped_column(String(16))
    degraded: Mapped[list] = mapped_column(JSON, default=list)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="analyst")  # analyst | admin
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    category: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(200))
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    brands: Mapped[list] = mapped_column(JSON, default=list)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # same id as the analysis
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending | approved | rejected
    auto_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    reporter_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel: Mapped[str] = mapped_column(String(16), default="web")
    source_kind: Mapped[str] = mapped_column(String(16), default="text")
    verdict: Mapped[str] = mapped_column(String(16))
    score: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8))
    redacted_text: Mapped[str] = mapped_column(Text)
    rule_ids: Mapped[list] = mapped_column(JSON, default=list)
    hard_rule_ids: Mapped[list] = mapped_column(JSON, default=list)
    brands: Mapped[list] = mapped_column(JSON, default=list)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    in_memory: Mapped[bool] = mapped_column(Boolean, default=False)


class Indicator(Base):
    __tablename__ = "report_indicators"
    __table_args__ = (Index("ix_indicator_kind_value", "kind", "value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # domain | url | phone_fp | account_fp
    value: Mapped[str] = mapped_column(String(500))
    # True when a deterministic link check confirmed this site (look-alike, Safe Browsing, homograph).
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WatchlistEntry(Base):
    __tablename__ = "watchlist"
    __table_args__ = (Index("ix_watchlist_kind_value", "kind", "value", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16))  # domain | phone_fp | account_fp
    value: Mapped[str] = mapped_column(String(255))
    # What analysts see: the domain itself, or a masked number such as 0300-***-4567.
    label: Mapped[str] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    added_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OfficialDomainExtra(Base):
    __tablename__ = "official_domains_extra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default="platform")
    added_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AICache(Base):
    __tablename__ = "ai_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[dict] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)


class RuleSuggestion(Base):
    __tablename__ = "rule_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed | accepted | rejected
    signal: Mapped[str] = mapped_column(String(48))
    pattern: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    examples: Mapped[list] = mapped_column(JSON, default=list)
    test_results: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(64), default="none")
    created_by: Mapped[str] = mapped_column(String(255))
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class FamilyLink(Base):
    __tablename__ = "family_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    member_hash: Mapped[str] = mapped_column(String(32), index=True)
    # Telegram chat that receives the alerts. Needed to send them; deleted when the link is removed.
    guardian_chat_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertLog(Base):
    __tablename__ = "alert_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # weekly | family
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)

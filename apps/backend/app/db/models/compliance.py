"""
ComplianceCheck  — one check run per script or publication.
RiskFlag         — one flag per detected risk within a check.

Status lifecycle
────────────────
  pending → running → passed | flagged | blocked

  passed  : risk_score < 21  — safe to publish
  flagged : 21 ≤ score < 80  — human review recommended/required
  blocked : score ≥ 80       — do NOT publish without manual override

Risk categories
───────────────
  ad_safety         Monetization eligibility — weight 0.35
  copyright_risk    Legal infringement risk  — weight 0.30
  factual_risk      Misinformation / false claims — weight 0.20
  reused_content    Duplicate / recycled content — weight 0.10
  ai_disclosure     AI-generated disclosure requirement — weight 0.05

Risk scoring
────────────
  Flag severity → raw score: critical 100 / high 70 / medium 40 / low 15 / info 0
  Category score = max(flag raw scores in that category)
  Overall risk_score = Σ(category_weight × category_score), range 0–100

Tiers (risk_score):
  0–20   → passed
  21–79  → flagged
  80–100 → blocked

Modes
─────
  rule  : deterministic regex/keyword checks (always run synchronously)
  ai    : LLM-powered deep analysis (dispatched as Celery task)
  both  : full run (default for production)
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.db.models.channel import Channel
    from app.db.models.publication import Publication
    from app.db.models.script import Script


# ── Enums ─────────────────────────────────────────────────────────────────────

class CheckStatus(str, enum.Enum):
    pending  = "pending"
    running  = "running"
    passed   = "passed"
    flagged  = "flagged"
    blocked  = "blocked"
    error    = "error"


class CheckMode(str, enum.Enum):
    rule = "rule"
    ai   = "ai"
    both = "both"


class RiskCategory(str, enum.Enum):
    ad_safety        = "ad_safety"
    copyright_risk   = "copyright_risk"
    factual_risk     = "factual_risk"
    reused_content   = "reused_content"
    ai_disclosure    = "ai_disclosure"


class RiskSeverity(str, enum.Enum):
    critical = "critical"   # score 100 — definite violation
    high     = "high"       # score 70  — likely violation
    medium   = "medium"     # score 40  — possible violation, review needed
    low      = "low"        # score 15  — minor concern
    info     = "info"       # score 0   — informational only


class FlagSource(str, enum.Enum):
    rule = "rule"   # regex / keyword match
    ai   = "ai"     # LLM analysis


# ── ComplianceCheck ───────────────────────────────────────────────────────────

class ComplianceCheck(Base, UUIDMixin, TimestampMixin):
    """
    One complete compliance check run.

    Can target a Script (pre-publication) or Publication (post-upload review).
    Script-level is the primary use case — catches issues before production cost.

    risk_score: 0–100.  Higher = more dangerous.
    passed_categories: JSON list of category names with score < 21.
    blocked_categories: JSON list of category names with score ≥ 80.

    override_by / override_reason: human can unlock a blocked check.
    """

    __tablename__ = "compliance_checks"
    __table_args__ = (
        Index("ix_cc_script",      "script_id"),
        Index("ix_cc_publication", "publication_id"),
        Index("ix_cc_status",      "status"),
        Index("ix_cc_channel",     "channel_id"),
    )

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    script_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scripts.id", ondelete="CASCADE"),
        nullable=True,
    )
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="SET NULL"),
        nullable=True,
    )

    mode: Mapped[CheckMode] = mapped_column(
        Enum(CheckMode, name="check_mode"),
        nullable=False,
        default=CheckMode.both,
    )
    status: Mapped[CheckStatus] = mapped_column(
        Enum(CheckStatus, name="check_status"),
        nullable=False,
        default=CheckStatus.pending,
    )

    # Overall risk score 0–100
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Per-category scores (JSON: {category: score})
    category_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Aggregated counts
    flag_count:    Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_count:    Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Monetization eligibility (derived from ad_safety category score)
    monetization_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # AI disclosure required (derived from ai_disclosure category)
    ai_disclosure_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Human override (unlock a blocked check)
    is_overridden:    Mapped[bool]        = mapped_column(Boolean, nullable=False, default=False)
    override_by:      Mapped[str | None]  = mapped_column(String(255), nullable=True)
    override_reason:  Mapped[str | None]  = mapped_column(Text, nullable=True)
    overridden_at:    Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timing
    started_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Celery task IDs for AI checks (JSON: {category: task_id})
    ai_task_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    flags:       Mapped[list["RiskFlag"]] = relationship(
        "RiskFlag",
        back_populates="check",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="RiskFlag.severity",
    )
    script:      Mapped["Script | None"]      = relationship("Script")
    publication: Mapped["Publication | None"] = relationship("Publication")

    def __repr__(self) -> str:
        target = f"script={self.script_id}" if self.script_id else f"pub={self.publication_id}"
        return f"<ComplianceCheck {target} {self.status.value} score={self.risk_score:.1f}>"


# ── RiskFlag ──────────────────────────────────────────────────────────────────

class RiskFlag(Base, UUIDMixin):
    """
    Individual risk signal within a ComplianceCheck.

    One flag per identified problem.  Multiple flags may exist for same category
    (e.g. three copyright violations = three flags).

    evidence: raw text excerpt or pattern that triggered the flag.
    suggestion: actionable fix the creator can apply.
    rule_id: machine-readable identifier for the rule (e.g. "ad_safety:profanity:f001").
    """

    __tablename__ = "risk_flags"
    __table_args__ = (
        Index("ix_rf_check",    "check_id"),
        Index("ix_rf_category", "category"),
        Index("ix_rf_severity", "severity"),
    )

    check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("compliance_checks.id", ondelete="CASCADE"),
        nullable=False,
    )

    category: Mapped[RiskCategory] = mapped_column(
        Enum(RiskCategory, name="risk_category"),
        nullable=False,
    )
    severity: Mapped[RiskSeverity] = mapped_column(
        Enum(RiskSeverity, name="risk_severity"),
        nullable=False,
    )
    source: Mapped[FlagSource] = mapped_column(
        Enum(FlagSource, name="flag_source"),
        nullable=False,
    )

    rule_id:    Mapped[str]          = mapped_column(String(100), nullable=False)
    title:      Mapped[str]          = mapped_column(String(300), nullable=False)
    detail:     Mapped[str]          = mapped_column(Text, nullable=False)
    evidence:   Mapped[str | None]   = mapped_column(Text, nullable=True)
    suggestion: Mapped[str | None]   = mapped_column(Text, nullable=True)

    # Position in source text (for highlighting)
    text_start: Mapped[int | None]   = mapped_column(Integer, nullable=True)
    text_end:   Mapped[int | None]   = mapped_column(Integer, nullable=True)

    # False-positive tracking
    is_dismissed:    Mapped[bool]       = mapped_column(Boolean, nullable=False, default=False)
    dismissed_by:    Mapped[str | None] = mapped_column(String(255), nullable=True)
    dismissed_at:    Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    check: Mapped["ComplianceCheck"] = relationship("ComplianceCheck", back_populates="flags")

    def __repr__(self) -> str:
        return f"<RiskFlag {self.category.value}:{self.severity.value} [{self.rule_id}]>"

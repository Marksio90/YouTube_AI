import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Literals ─────────────────────────────────────────────────────────────────

CheckStatusType  = Literal["pending", "running", "passed", "flagged", "blocked", "error"]
CheckModeType    = Literal["rule", "ai", "both"]
RiskCategoryType = Literal["ad_safety", "copyright_risk", "factual_risk", "reused_content", "ai_disclosure"]
RiskSeverityType = Literal["critical", "high", "medium", "low", "info"]
FlagSourceType   = Literal["rule", "ai"]


# ── RiskFlag ──────────────────────────────────────────────────────────────────

class RiskFlagRead(BaseModel):
    id: uuid.UUID
    check_id: uuid.UUID
    category: RiskCategoryType
    severity: RiskSeverityType
    source: FlagSourceType
    rule_id: str
    title: str
    detail: str
    evidence: str | None
    suggestion: str | None
    text_start: int | None
    text_end: int | None
    is_dismissed: bool
    dismissed_by: str | None
    dismissed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskFlagDismiss(BaseModel):
    dismissed_by: str = Field(min_length=1, max_length=255)
    reason: str | None = None


# ── ComplianceCheck ───────────────────────────────────────────────────────────

class ComplianceCheckRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    script_id: uuid.UUID | None
    publication_id: uuid.UUID | None
    mode: CheckModeType
    status: CheckStatusType
    risk_score: float
    category_scores: dict[str, float]
    flag_count: int
    critical_count: int
    high_count: int
    monetization_eligible: bool
    ai_disclosure_required: bool
    is_overridden: bool
    override_by: str | None
    override_reason: str | None
    overridden_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    flags: list[RiskFlagRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ComplianceCheckCreate(BaseModel):
    script_id: uuid.UUID | None = None
    publication_id: uuid.UUID | None = None
    mode: CheckModeType = "both"


class ComplianceCheckOverride(BaseModel):
    override_by: str = Field(min_length=1, max_length=255)
    override_reason: str = Field(min_length=10, max_length=2000)


# ── Summary views ─────────────────────────────────────────────────────────────

class CategoryBreakdown(BaseModel):
    category: RiskCategoryType
    score: float
    flag_count: int
    worst_severity: RiskSeverityType | None
    flags: list[RiskFlagRead]


class ComplianceCheckDetail(ComplianceCheckRead):
    """Full check result with per-category breakdown."""
    categories: list[CategoryBreakdown]


class ComplianceSummary(BaseModel):
    """Lightweight summary for list views."""
    id: uuid.UUID
    script_id: uuid.UUID | None
    publication_id: uuid.UUID | None
    status: CheckStatusType
    risk_score: float
    flag_count: int
    critical_count: int
    monetization_eligible: bool
    ai_disclosure_required: bool
    is_overridden: bool
    created_at: datetime

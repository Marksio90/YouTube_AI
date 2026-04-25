"""
Deprecated compatibility wrapper.

Use `worker.agents.compliance.ComplianceAgent` with `.run(...)` instead.
"""
from __future__ import annotations

import warnings

from worker.agents.compliance import ComplianceAgent, ComplianceInput


class ComplianceCheckerAgent(ComplianceAgent):
    def __init__(self, *args, **kwargs) -> None:
        warnings.warn(
            "ComplianceCheckerAgent is deprecated. Use ComplianceAgent.run(...) with ComplianceInput.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)

    async def check(self, *, title: str, script: str, channel_niche: str = "general") -> dict:
        out = await self.run(
            ComplianceInput(
                title=title,
                script=script,
                niche=channel_niche,
            )
        )
        if out.risk_level in {"safe", "low"}:
            status = "PASS"
        elif out.risk_level in {"medium", "high"}:
            status = "WARNING"
        else:
            status = "BLOCK"

        return {
            "overall_status": status,
            "compliance_score": out.advertiser_friendly_score,
            "monetization_eligible": out.monetization_eligible,
            "issues": [v.model_dump() for v in out.violations],
            "summary": out.review_notes,
            "risk_level": out.risk_level,
            "warnings": out.warnings,
            "suggestions": out.suggestions,
        }

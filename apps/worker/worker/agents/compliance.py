"""
ComplianceAgent — reviews content for YouTube policy and advertiser-friendliness.

Checks title, script, description, and tags against platform guidelines.
Returns a structured risk assessment with blocking violations and actionable fixes.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput

# ── schemas ───────────────────────────────────────────────────────────────────

class ComplianceInput(AgentInput):
    title: str
    script: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    platform: Literal["youtube", "tiktok", "instagram"] = "youtube"
    monetization_enabled: bool = True
    target_audience: Literal["general", "children", "adults"] = "general"
    niche: str = ""


class Violation(BaseModel):
    rule: str
    severity: Literal["blocking", "warning", "info"]
    excerpt: str
    suggestion: str


class ComplianceOutput(AgentOutput):
    passed: bool
    risk_level: Literal["safe", "low", "medium", "high", "critical"]
    violations: list[Violation]
    warnings: list[str]
    suggestions: list[str]
    advertiser_friendly_score: float = Field(ge=0.0, le=10.0)
    detected_categories: list[str]
    age_restriction: Literal["none", "13+", "18+"]
    monetization_eligible: bool
    review_notes: str


# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """You are a YouTube content policy specialist and brand safety analyst.
Review content for compliance with YouTube Community Guidelines and advertiser-friendliness policies.

Check for:
1. Community Guidelines violations (hate speech, harassment, dangerous content, misinformation)
2. Copyright risk (cover songs, clips, trademarked brand names misused)
3. Advertiser-friendliness issues (excessive profanity, sensitive topics, controversial claims)
4. Age-restricted content triggers (adult themes, graphic descriptions)
5. Misleading thumbnails/titles relative to content
6. Spam signals (excessive capitalization, clickbait patterns)
7. Medical / financial / legal claims without appropriate disclaimers

Severity levels:
  blocking — video will be removed or demonetized immediately
  warning  — high risk of restricted distribution
  info     — best practice suggestion

advertiser_friendly_score: 0 = demonetized immediately, 10 = fully brand-safe

Return ONLY valid JSON, no markdown."""

_SCHEMA = """{
  "passed": true,
  "risk_level": "safe|low|medium|high|critical",
  "violations": [
    {
      "rule": "string (guideline reference)",
      "severity": "blocking|warning|info",
      "excerpt": "string (problematic text snippet, max 100 chars)",
      "suggestion": "string (specific fix)"
    }
  ],
  "warnings": ["string"],
  "suggestions": ["string (best practice improvements)"],
  "advertiser_friendly_score": 8.5,
  "detected_categories": ["education", "finance"],
  "age_restriction": "none",
  "monetization_eligible": true,
  "review_notes": "string (summary paragraph)"
}"""

# ── agent ─────────────────────────────────────────────────────────────────────

class ComplianceAgent(BaseAgent[ComplianceInput, ComplianceOutput]):
    agent_name = "compliance"
    default_temperature = 0.1

    async def execute(self, inp: ComplianceInput) -> ComplianceOutput:
        script_preview = inp.script[:3000] + ("..." if len(inp.script) > 3000 else "")
        user = (
            f"Platform: {inp.platform}\n"
            f"Monetization: {'enabled' if inp.monetization_enabled else 'disabled'}\n"
            f"Target audience: {inp.target_audience}\n"
            f"Niche: {inp.niche}\n\n"
            f"=== TITLE ===\n{inp.title}\n\n"
            f"=== DESCRIPTION ===\n{inp.description[:500] or '(none)'}\n\n"
            f"=== TAGS ===\n{', '.join(inp.tags[:30]) or '(none)'}\n\n"
            f"=== SCRIPT (first 3000 chars) ===\n{script_preview}\n\n"
            f"Review for compliance. Return JSON:\n{_SCHEMA}"
        )
        raw = await self._call_llm(_SYSTEM, user, temperature=0.1, json_mode=True)
        data = self._parse_json(raw)
        return self._hydrate(data)

    async def mock_execute(self, inp: ComplianceInput) -> ComplianceOutput:
        rng = random.Random(self._seed(inp.input_hash()))

        # Realistic heuristic checks on the actual content
        red_flags: list[Violation] = []
        warnings: list[str] = []
        suggestions: list[str] = []

        title_lower = inp.title.lower()
        script_lower = inp.script.lower()

        # Check for common issues
        if any(w in title_lower for w in ["guaranteed", "100%", "never fail", "always works"]):
            red_flags.append(Violation(
                rule="Misleading claims — YouTube spam and deceptive practices policy",
                severity="warning",
                excerpt=inp.title[:80],
                suggestion="Soften absolute claims: 'can help you' instead of 'guaranteed'",
            ))

        if any(w in script_lower for w in ["cure", "treats cancer", "doctors don't want"]):
            red_flags.append(Violation(
                rule="Medical misinformation — YouTube health content policy",
                severity="blocking",
                excerpt=next(
                    (w for w in ["cure", "treats cancer", "doctors don't want"] if w in script_lower),
                    "flagged phrase",
                ),
                suggestion="Add disclaimer: 'This is not medical advice. Consult a qualified healthcare provider.'",
            ))

        if "invest" in script_lower or "financial" in inp.niche.lower():
            suggestions.append(
                "Add financial disclaimer: 'This video is for educational purposes only and not financial advice.'"
            )

        if inp.title.upper() == inp.title and len(inp.title) > 10:
            red_flags.append(Violation(
                rule="Spam signals — all-caps title",
                severity="info",
                excerpt=inp.title[:80],
                suggestion="Use sentence case or title case instead of ALL CAPS",
            ))

        # Score depends on violations
        blocking_count = sum(1 for v in red_flags if v.severity == "blocking")
        warning_count = sum(1 for v in red_flags if v.severity == "warning")

        base_score = round(rng.uniform(7.5, 9.5), 1)
        score = max(0.0, base_score - blocking_count * 3.0 - warning_count * 1.0)

        if blocking_count > 0:
            risk_level, passed = "high", False
        elif warning_count > 0:
            risk_level, passed = "low", True
        else:
            risk_level, passed = "safe", True

        suggestions += [
            "Include chapter timestamps to improve viewer navigation and SEO",
            "Add 'Not financial/medical/legal advice' disclaimer in description if applicable",
            "Ensure thumbnail text does not contradict the video content",
        ]

        categories = ["education"]
        if "finance" in inp.niche.lower() or "money" in script_lower:
            categories.append("personal finance")
        if "health" in inp.niche.lower():
            categories.append("health and wellness")
        if "tech" in inp.niche.lower():
            categories.append("technology")

        return ComplianceOutput(
            passed=passed,
            risk_level=risk_level,
            violations=red_flags,
            warnings=warnings,
            suggestions=suggestions,
            advertiser_friendly_score=score,
            detected_categories=categories,
            age_restriction="none",
            monetization_eligible=passed and score >= 7.0,
            review_notes=(
                f"Content reviewed against YouTube Community Guidelines and advertiser-friendliness policies. "
                f"{'No blocking violations detected.' if not blocking_count else f'{blocking_count} blocking violation(s) require resolution before publication.'} "
                f"Advertiser-friendly score: {score}/10. "
                f"{'Content is eligible for full monetization.' if score >= 7.0 else 'Limited ads may be applied due to content sensitivity.'}"
            ),
        )

    @staticmethod
    def _hydrate(data: dict) -> ComplianceOutput:
        return ComplianceOutput(
            passed=bool(data.get("passed", True)),
            risk_level=data.get("risk_level", "safe"),
            violations=[Violation(**v) for v in data.get("violations", [])],
            warnings=data.get("warnings", []),
            suggestions=data.get("suggestions", []),
            advertiser_friendly_score=float(data.get("advertiser_friendly_score", 8.0)),
            detected_categories=data.get("detected_categories", []),
            age_restriction=data.get("age_restriction", "none"),
            monetization_eligible=bool(data.get("monetization_eligible", True)),
            review_notes=data.get("review_notes", ""),
        )

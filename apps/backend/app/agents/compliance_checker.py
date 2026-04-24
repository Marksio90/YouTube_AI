import json

import structlog

from app.agents.base import BaseAgent

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a YouTube content compliance specialist.
Check scripts for policy violations and monetization eligibility.

Evaluate against:
1. YouTube Community Guidelines (hate speech, harassment, dangerous content)
2. YouTube Monetization Policies (advertiser-friendly content)
3. Copyright risk (overuse of third-party references)
4. GDPR/privacy (PII mentions, data collection)
5. Legal risk (defamation, medical/legal advice without disclaimers)

Severity levels: PASS | WARNING | BLOCK

Return valid JSON only. Be conservative: flag edge cases as WARNING."""

COMPLIANCE_OUTPUT_SCHEMA = """{
  "overall_status": "PASS|WARNING|BLOCK",
  "compliance_score": 9.2,
  "monetization_eligible": true,
  "issues": [
    {
      "type": "copyright|guidelines|privacy|legal",
      "severity": "WARNING",
      "description": "description of issue",
      "excerpt": "problematic text if applicable",
      "suggested_fix": "how to resolve"
    }
  ],
  "summary": "brief compliance summary"
}"""


class ComplianceCheckerAgent(BaseAgent):
    async def check(self, *, title: str, script: str, channel_niche: str = "general") -> dict:
        truncated = script[:4000] + "..." if len(script) > 4000 else script

        user_message = f"""Check this YouTube script for policy compliance:

Title: {title}
Niche: {channel_niche}
Script: {truncated}

Return ONLY valid JSON matching this schema:
{COMPLIANCE_OUTPUT_SCHEMA}"""

        logger.info("compliance_checker.check", title=title[:60])

        raw = await self._call(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.1,
        )

        return json.loads(raw)

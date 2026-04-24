import json

from worker.agents.base import BaseAgent

SYSTEM_PROMPT = "You are a YouTube compliance specialist. Check for policy violations. Return valid JSON only."
SCHEMA = '{"overall_status":"PASS|WARNING|BLOCK","compliance_score":9.2,"monetization_eligible":true,"issues":[],"summary":"..."}'


class ComplianceCheckerAgent(BaseAgent):
    async def check(self, *, title: str, script: str, channel_niche: str = "general") -> dict:
        truncated = script[:3000] + "..." if len(script) > 3000 else script
        msg = f"Title: {title}\nNiche: {channel_niche}\nScript: {truncated}\n\nReturn ONLY JSON: {SCHEMA}"
        raw = await self._call(system=SYSTEM_PROMPT, messages=[{"role": "user", "content": msg}], temperature=0.1)
        return json.loads(raw)

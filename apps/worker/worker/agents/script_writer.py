import json
import re

from worker.agents.base import BaseAgent

SYSTEM_PROMPT = """You are an expert YouTube script writer specializing in no-face content.
Structure: HOOK (0-30s) → BODY (sections) → CTA. Return valid JSON only."""

SCHEMA = '{"title":"string","hook":"string","body":"string","cta":"string","keywords":["..."],"estimated_duration_seconds":600,"seo_score":8.5}'


class ScriptWriterAgent(BaseAgent):
    async def generate(self, *, topic: str, tone: str, target_duration_seconds: int = 600, keywords: list[str] | None = None, channel_niche: str = "general", additional_context: str | None = None) -> dict:
        msg = f"Topic: {topic}\nNiche: {channel_niche}\nTone: {tone}\nDuration: {target_duration_seconds}s\nKeywords: {', '.join(keywords or [])}\n{f'Context: {additional_context}' if additional_context else ''}\n\nReturn ONLY JSON: {SCHEMA}"
        raw = await self._call(system=SYSTEM_PROMPT, messages=[{"role": "user", "content": msg}], temperature=0.8)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                raise ValueError("Non-JSON response from ScriptWriterAgent")
            return json.loads(m.group())

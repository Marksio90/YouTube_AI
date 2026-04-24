import json

import structlog

from app.agents.base import BaseAgent

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are an expert YouTube script writer specializing in no-face content.
Your scripts are optimized for watch time, SEO, and monetization.

Structure every script with:
1. HOOK (0-30s): Pattern interrupt that stops the scroll. Never start with "In this video..."
2. BODY: Value delivery with clear sections. Each section ends with a micro-retention hook.
3. CTA: Specific call-to-action tied to the value delivered.

Tone guidelines:
- educational: clear, structured, authoritative but accessible
- entertaining: fast-paced, energetic, with story elements
- inspirational: emotional arc, relatable struggle → transformation
- controversial: balanced presentation of opposing views, never clickbait
- news: factual, timely, analytical

Always return valid JSON matching the ScriptOutput schema."""

SCRIPT_OUTPUT_SCHEMA = """{
  "title": "string (SEO-optimized, max 100 chars)",
  "hook": "string (first 30 seconds of script, max 500 chars)",
  "body": "string (full body with [SECTION: name] markers)",
  "cta": "string (call to action, max 300 chars)",
  "keywords": ["array", "of", "seo", "keywords"],
  "estimated_duration_seconds": 600,
  "seo_score": 8.5,
  "notes": "string (brief production notes)"
}"""


class ScriptWriterAgent(BaseAgent):
    async def generate(
        self,
        *,
        topic: str,
        tone: str,
        target_duration_seconds: int = 600,
        keywords: list[str] | None = None,
        channel_niche: str = "general",
        additional_context: str | None = None,
    ) -> dict:
        keyword_str = ", ".join(keywords or []) or "none specified"
        duration_min = target_duration_seconds // 60

        user_message = f"""Generate a YouTube script for the following:

Topic: {topic}
Niche: {channel_niche}
Tone: {tone}
Target duration: {duration_min} minutes ({target_duration_seconds} seconds)
Keywords to include: {keyword_str}
{f'Additional context: {additional_context}' if additional_context else ''}

Return ONLY valid JSON matching this schema:
{SCRIPT_OUTPUT_SCHEMA}"""

        logger.info("script_writer.generate", topic=topic, tone=tone, duration=target_duration_seconds)

        raw = await self._call(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.8,
        )

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not json_match:
                raise ValueError(f"Agent returned non-JSON response: {raw[:200]}")
            result = json.loads(json_match.group())

        return result

import json

import structlog

from app.agents.base import BaseAgent

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a YouTube SEO specialist with deep knowledge of the algorithm.
Analyze scripts and titles for SEO optimization.

Scoring criteria (0-10 each, averaged):
- Keyword density and placement (title, hook, body, tags)
- Search intent alignment
- Title click-through potential (CTR)
- Watch time optimization signals
- Trend relevance

Return valid JSON only."""

SEO_OUTPUT_SCHEMA = """{
  "overall_score": 8.5,
  "title_score": 9.0,
  "keyword_coverage": 7.5,
  "search_intent_match": 8.0,
  "suggested_title": "Improved title if needed",
  "suggested_tags": ["tag1", "tag2"],
  "improvement_notes": ["specific action 1", "specific action 2"]
}"""


class SEOAnalyzerAgent(BaseAgent):
    async def analyze(
        self,
        *,
        title: str,
        script_body: str,
        keywords: list[str],
        niche: str = "general",
    ) -> dict:
        truncated_body = script_body[:3000] + "..." if len(script_body) > 3000 else script_body

        user_message = f"""Analyze this YouTube content for SEO:

Title: {title}
Niche: {niche}
Target keywords: {', '.join(keywords)}
Script (excerpt): {truncated_body}

Return ONLY valid JSON matching this schema:
{SEO_OUTPUT_SCHEMA}"""

        logger.info("seo_analyzer.analyze", title=title[:60], niche=niche)

        raw = await self._call(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.3,
        )

        return json.loads(raw)

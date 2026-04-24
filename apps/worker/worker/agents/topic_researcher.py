"""
TopicResearcherAgent — discovers and scores content topics for a channel.

discover():  Given a channel niche, returns N fresh topic ideas with metadata.
score():     Given an existing topic, returns a numeric trend/potential score.
"""

import structlog

from worker.agents.base import BaseAgent

log = structlog.get_logger(__name__)

_DISCOVER_SYSTEM = """You are a YouTube content strategist specializing in no-face (faceless) channels.
Your job: identify high-potential video topics for a given niche.

For each topic provide:
- Estimated search volume tier: low / medium / high / very_high
- Competition level: low / medium / high
- Monetization potential: low / medium / high (based on advertiser interest)
- Content angle: the specific hook/twist that makes it stand out
- Estimated trend trajectory: rising / stable / declining

Return ONLY valid JSON. No markdown, no explanation."""

_DISCOVER_SCHEMA = """{
  "topics": [
    {
      "title": "string (max 100 chars, YouTube-ready title)",
      "description": "string (2-3 sentences, what the video covers)",
      "keywords": ["keyword1", "keyword2", "keyword3"],
      "search_volume": "medium",
      "competition": "low",
      "monetization_potential": "high",
      "content_angle": "string",
      "trend": "rising",
      "estimated_views_30d": 15000
    }
  ]
}"""

_SCORE_SYSTEM = """You are a YouTube SEO and trend analyst.
Score the given topic on its current viability for a faceless YouTube channel.
Return ONLY valid JSON."""

_SCORE_SCHEMA = """{
  "trend_score": 7.4,
  "search_demand": 8.0,
  "competition_score": 6.5,
  "monetization_score": 8.5,
  "overall_score": 7.6,
  "rationale": "brief explanation",
  "suggested_title_variants": ["variant 1", "variant 2"],
  "best_publish_window": "string (e.g. Tuesday-Thursday, 14:00-18:00 UTC)"
}"""


class TopicResearcherAgent(BaseAgent):
    async def discover(
        self,
        *,
        niche: str,
        channel_name: str,
        existing_titles: list[str] | None = None,
        count: int = 10,
    ) -> list[dict]:
        avoid_block = ""
        if existing_titles:
            avoid = "\n".join(f"- {t}" for t in existing_titles[:20])
            avoid_block = f"\n\nAvoid these already-covered topics:\n{avoid}"

        user_msg = (
            f"Channel niche: {niche}\n"
            f"Channel name: {channel_name}\n"
            f"Generate exactly {count} high-potential topic ideas for a faceless YouTube channel.{avoid_block}\n\n"
            f"Return JSON:\n{_DISCOVER_SCHEMA}"
        )

        log.info("topic_researcher.discover", niche=niche, count=count)
        result = await self._call_json(_DISCOVER_SYSTEM, user_msg, temperature=0.9)
        return result.get("topics", [])

    async def score(
        self,
        *,
        title: str,
        description: str,
        keywords: list[str],
        niche: str,
    ) -> dict:
        user_msg = (
            f"Niche: {niche}\n"
            f"Topic title: {title}\n"
            f"Description: {description}\n"
            f"Keywords: {', '.join(keywords)}\n\n"
            f"Score this topic. Return JSON:\n{_SCORE_SCHEMA}"
        )

        log.info("topic_researcher.score", title=title[:80])
        return await self._call_json(_SCORE_SYSTEM, user_msg, temperature=0.2)

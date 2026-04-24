"""
TopicResearcherAgent — discovers and scores content topics for a channel.
Migrated to new BaseAgent — uses provider abstraction and full tracing.
Prefer ScoutAgent + OpportunityScorerAgent + ResearchAgent for new workflows.
"""
from __future__ import annotations

import structlog

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput

log = structlog.get_logger(__name__)

_DISCOVER_SYSTEM = """You are a YouTube content strategist specializing in no-face (faceless) channels.
Your job: identify high-potential video topics for a given niche.
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


class _Noop(AgentInput):
    pass


class _NoopOut(AgentOutput):
    pass


class TopicResearcherAgent(BaseAgent[_Noop, _NoopOut]):
    """
    Legacy free-form interface for tasks/topics.py.
    Uses new BaseAgent provider abstraction and _call_json helper.
    """

    agent_name = "topic_researcher"
    default_temperature = 0.7

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

        user = (
            f"Channel niche: {niche}\n"
            f"Channel name: {channel_name}\n"
            f"Generate exactly {count} high-potential topic ideas for a faceless YouTube channel.{avoid_block}\n\n"
            f"Return JSON:\n{_DISCOVER_SCHEMA}"
        )
        log.info("topic_researcher.discover", niche=niche, count=count)
        result = await self._call_json(_DISCOVER_SYSTEM, user, temperature=0.9)
        return result.get("topics", [])

    async def score(
        self,
        *,
        title: str,
        description: str,
        keywords: list[str],
        niche: str,
    ) -> dict:
        user = (
            f"Niche: {niche}\n"
            f"Topic title: {title}\n"
            f"Description: {description}\n"
            f"Keywords: {', '.join(keywords)}\n\n"
            f"Score this topic. Return JSON:\n{_SCORE_SCHEMA}"
        )
        log.info("topic_researcher.score", title=title[:80])
        return await self._call_json(_SCORE_SYSTEM, user, temperature=0.2)

    async def execute(self, inp: _Noop) -> _NoopOut:
        return _NoopOut()

    async def mock_execute(self, inp: _Noop) -> _NoopOut:
        return _NoopOut()

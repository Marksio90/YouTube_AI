"""
RecommenderAgent — generates content strategy recommendations.

Analyzes channel performance data (top videos, analytics trends, topic inventory)
and returns actionable recommendations for the next content cycle.
"""

import structlog

from worker.agents.base import BaseAgent

log = structlog.get_logger(__name__)

_SYSTEM = """You are a YouTube channel growth strategist specializing in faceless (no-face) content.
You analyze performance data and generate concrete, actionable recommendations.

Focus on:
1. Content gaps — topics the audience wants but the channel hasn't covered
2. Format opportunities — video lengths, styles that perform best on this channel
3. SEO opportunities — keywords with growing search volume and low competition
4. Monetization — topics that attract high-CPM advertisers
5. Publishing cadence — optimal schedule based on analytics

Return ONLY valid JSON. No markdown, no preamble."""

_SCHEMA = """{
  "summary": "string (2-3 sentence channel health summary)",
  "priority_topics": [
    {
      "title": "string",
      "rationale": "string",
      "urgency": "high|medium|low",
      "estimated_views": 20000
    }
  ],
  "format_recommendations": [
    {
      "format": "string (e.g. '8-12 min listicle')",
      "rationale": "string"
    }
  ],
  "seo_opportunities": [
    {
      "keyword": "string",
      "monthly_searches": 5000,
      "competition": "low|medium|high"
    }
  ],
  "publishing_schedule": {
    "optimal_days": ["Tuesday", "Thursday"],
    "optimal_time_utc": "15:00",
    "recommended_frequency": "2x per week"
  },
  "avoid": ["string - topics/formats to avoid and why"]
}"""


class RecommenderAgent(BaseAgent):
    async def generate(
        self,
        *,
        channel_name: str,
        niche: str,
        top_videos: list[dict],
        analytics_summary: dict,
        existing_topics: list[str],
    ) -> dict:
        top_videos_block = "\n".join(
            f"- '{v.get('title', '')}' — {v.get('view_count', 0):,} views, "
            f"${v.get('revenue_usd', 0):.2f} revenue"
            for v in top_videos[:10]
        )

        user_msg = (
            f"Channel: {channel_name}\n"
            f"Niche: {niche}\n\n"
            f"=== TOP PERFORMING VIDEOS (last 90d) ===\n{top_videos_block or 'No data yet'}\n\n"
            f"=== ANALYTICS SUMMARY (last 28d) ===\n"
            f"Views: {analytics_summary.get('total_views', 0):,}\n"
            f"Revenue: ${analytics_summary.get('total_revenue_usd', 0):.2f}\n"
            f"Avg RPM: ${analytics_summary.get('avg_rpm', 0):.2f}\n"
            f"Subscribers gained: {analytics_summary.get('subscribers_gained', 0)}\n\n"
            f"=== EXISTING TOPIC PIPELINE ===\n"
            + "\n".join(f"- {t}" for t in existing_topics[:20])
            + f"\n\nGenerate recommendations. Return JSON:\n{_SCHEMA}"
        )

        log.info("recommender.generate", channel=channel_name, niche=niche)
        return await self._call_json(_SYSTEM, user_msg, temperature=0.7)

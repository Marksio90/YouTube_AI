"""
OpportunityScorerAgent — multi-dimensional scoring of a single content opportunity.

Evaluates search demand, competition, monetization, timeliness, and channel fit.
Returns a structured score with a clear pursue / consider / monitor / skip recommendation.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput

# ── schemas ───────────────────────────────────────────────────────────────────

class OpportunityScorerInput(AgentInput):
    topic: str
    description: str = ""
    niche: str
    keywords: list[str] = Field(default_factory=list)
    existing_topics: list[str] = Field(default_factory=list)
    channel_subscribers: int = 0
    channel_avg_views: int = 0


class DimensionScore(BaseModel):
    dimension: str
    score: float = Field(ge=0.0, le=10.0)
    rationale: str


class OpportunityScorerOutput(AgentOutput):
    topic: str
    overall_score: float = Field(ge=0.0, le=10.0)
    scores: list[DimensionScore]
    recommendation: Literal["pursue", "consider", "monitor", "skip"]
    priority: Literal["high", "medium", "low"]
    best_publish_window: str
    title_variants: list[str]
    risks: list[str]
    opportunities: list[str]


# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """You are a YouTube content opportunity analyst scoring topics for faceless educational channels.

Score each topic across five dimensions (0-10 each):
1. search_demand      — monthly search volume potential for the keyword cluster
2. competition        — inverse saturation score (10 = almost no strong competitors)
3. monetization       — advertiser CPM interest (finance/SaaS keywords = higher)
4. timeliness         — relevance right now vs. 6 months from now
5. channel_fit        — suitability for a faceless, narration-only educational format

Recommendation thresholds:
  pursue   → overall ≥ 7.5
  consider → 6.0–7.4
  monitor  → 4.5–5.9
  skip     → < 4.5

Return ONLY valid JSON, no markdown."""

_SCHEMA = """{
  "overall_score": 7.8,
  "scores": [
    {"dimension": "search_demand",   "score": 8.5, "rationale": "string"},
    {"dimension": "competition",     "score": 7.0, "rationale": "string"},
    {"dimension": "monetization",    "score": 9.0, "rationale": "string"},
    {"dimension": "timeliness",      "score": 6.5, "rationale": "string"},
    {"dimension": "channel_fit",     "score": 7.8, "rationale": "string"}
  ],
  "recommendation": "pursue",
  "priority": "high",
  "best_publish_window": "Tuesday or Thursday, 14:00-18:00 UTC",
  "title_variants": ["variant 1", "variant 2", "variant 3"],
  "risks": ["risk 1", "risk 2"],
  "opportunities": ["opportunity 1", "opportunity 2"]
}"""

# ── agent ─────────────────────────────────────────────────────────────────────

class OpportunityScorerAgent(BaseAgent[OpportunityScorerInput, OpportunityScorerOutput]):
    agent_name = "opportunity_scorer"
    default_temperature = 0.2

    async def execute(self, inp: OpportunityScorerInput) -> OpportunityScorerOutput:
        existing_block = (
            "\nAlready covered topics (penalise overlap):\n"
            + "\n".join(f"- {t}" for t in inp.existing_topics[:20])
            if inp.existing_topics else ""
        )
        user = (
            f"Topic: {inp.topic}\n"
            f"Description: {inp.description}\n"
            f"Niche: {inp.niche}\n"
            f"Keywords: {', '.join(inp.keywords)}\n"
            f"Channel: {inp.channel_subscribers:,} subscribers, ~{inp.channel_avg_views:,} avg views"
            f"{existing_block}\n\nScore this opportunity. Return JSON:\n{_SCHEMA}"
        )
        raw = await self._call_llm(_SYSTEM, user, temperature=0.2, json_mode=True)
        data = self._parse_json(raw)
        return self._build_output(inp.topic, data)

    async def mock_execute(self, inp: OpportunityScorerInput) -> OpportunityScorerOutput:
        rng = random.Random(self._seed(inp.input_hash()))

        raw_scores = {
            "search_demand": round(rng.uniform(5.0, 9.5), 1),
            "competition":   round(rng.uniform(4.5, 8.5), 1),
            "monetization":  round(rng.uniform(5.5, 9.5), 1),
            "timeliness":    round(rng.uniform(5.0, 8.5), 1),
            "channel_fit":   round(rng.uniform(6.0, 9.0), 1),
        }
        rationales = {
            "search_demand": f"'{inp.topic}' shows consistent monthly search volume with Q1 and Q4 spikes.",
            "competition":   "Top-ranking videos are 12-24 months old with declining engagement — gap available.",
            "monetization":  f"Keyword cluster attracts high-CPM advertisers ($8-$22 CPM range estimated).",
            "timeliness":    "Topic is structurally evergreen with recurring news cycles extending relevance.",
            "channel_fit":   "Faceless narration-over-animation is the dominant format in this keyword cluster.",
        }
        overall = round(sum(raw_scores.values()) / len(raw_scores), 1)

        if overall >= 7.5:
            rec, pri = "pursue", "high"
        elif overall >= 6.0:
            rec, pri = "consider", "medium"
        elif overall >= 4.5:
            rec, pri = "monitor", "low"
        else:
            rec, pri = "skip", "low"

        return OpportunityScorerOutput(
            topic=inp.topic,
            overall_score=overall,
            scores=[
                DimensionScore(dimension=dim, score=score, rationale=rationales[dim])
                for dim, score in raw_scores.items()
            ],
            recommendation=rec,
            priority=pri,
            best_publish_window="Tuesday or Thursday, 14:00–17:00 UTC",
            title_variants=[
                f"{inp.topic}: The Complete 2024 Guide",
                f"Everything You Need to Know About {inp.topic}",
                f"Why Most People Get {inp.topic} Completely Wrong",
            ],
            risks=[
                "High-authority channels may enter this keyword cluster within 60 days",
                "Topic accuracy requires periodic updates as the landscape evolves",
            ],
            opportunities=[
                "Strong affiliate and sponsorship monetization beyond AdSense",
                "Email list capture via free checklist lead magnet in description",
                "Repurpose into short-form clips for additional platform reach",
            ],
        )

    @staticmethod
    def _build_output(topic: str, data: dict) -> OpportunityScorerOutput:
        return OpportunityScorerOutput(
            topic=topic,
            overall_score=float(data.get("overall_score", 5.0)),
            scores=[DimensionScore(**s) for s in data.get("scores", [])],
            recommendation=data.get("recommendation", "consider"),
            priority=data.get("priority", "medium"),
            best_publish_window=data.get("best_publish_window", "Tuesday-Thursday, 14:00-17:00 UTC"),
            title_variants=data.get("title_variants", []),
            risks=data.get("risks", []),
            opportunities=data.get("opportunities", []),
        )

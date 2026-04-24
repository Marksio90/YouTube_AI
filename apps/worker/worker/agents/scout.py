"""
ScoutAgent — discovers high-potential content opportunities for a channel.

Scans the niche for trending topics, keyword gaps, and competitor blind spots.
Returns ranked opportunities ready for OpportunityScorerAgent to evaluate.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput

# ── schemas ───────────────────────────────────────────────────────────────────

class ScoutInput(AgentInput):
    niche: str
    channel_name: str
    days_back: int = Field(default=7, ge=1, le=90)
    count: int = Field(default=15, ge=1, le=50)
    competitor_channels: list[str] = Field(default_factory=list)
    keywords_to_include: list[str] = Field(default_factory=list)
    keywords_to_exclude: list[str] = Field(default_factory=list)


class ScoutedOpportunity(BaseModel):
    title: str
    content_angle: str
    search_volume_tier: Literal["low", "medium", "high", "very_high"]
    competition: Literal["low", "medium", "high"]
    monetization_potential: Literal["low", "medium", "high"]
    trend: Literal["rising", "stable", "declining", "viral"]
    estimated_views_30d: int
    target_audience: str
    hook_suggestion: str
    keywords: list[str]
    urgency: Literal["evergreen", "timely", "urgent"]


class ScoutOutput(AgentOutput):
    niche: str
    opportunities: list[ScoutedOpportunity]
    market_insights: str
    recommended_priority: list[str]
    next_refresh_hours: int


# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """You are a YouTube content intelligence analyst for faceless (no-face) channels.
You identify trending, monetizable video opportunities in a given niche.

For each opportunity:
- YouTube-ready title (max 80 chars, clickable)
- content_angle: specific hook/twist that differentiates it
- search_volume_tier: low (<1k/mo) | medium (1k-10k) | high (10k-100k) | very_high (>100k)
- competition: low | medium | high (saturation of strong existing videos)
- monetization_potential: low | medium | high (advertiser CPM interest)
- trend: rising | stable | declining | viral
- estimated_views_30d: realistic for a 10k-200k sub channel
- target_audience: 1-sentence description
- hook_suggestion: compelling opening line
- keywords: 3-5 SEO keywords
- urgency: evergreen | timely | urgent

Return ONLY valid JSON, no markdown."""

_SCHEMA = """{
  "opportunities": [
    {
      "title": "string",
      "content_angle": "string",
      "search_volume_tier": "high",
      "competition": "medium",
      "monetization_potential": "high",
      "trend": "rising",
      "estimated_views_30d": 25000,
      "target_audience": "string",
      "hook_suggestion": "string",
      "keywords": ["kw1", "kw2", "kw3"],
      "urgency": "evergreen"
    }
  ],
  "market_insights": "string (2-3 sentences on current niche dynamics)",
  "recommended_priority": ["title1", "title2", "title3"],
  "next_refresh_hours": 48
}"""

# ── mock data ─────────────────────────────────────────────────────────────────

_MOCK_TEMPLATES: dict[str, list[dict]] = {
    "finance": [
        {"title": "I Invested $1,000/Month for 10 Years — Here's The Result",
         "content_angle": "Compound interest visualized with real brokerage data",
         "search_volume_tier": "very_high", "competition": "medium",
         "monetization_potential": "high", "trend": "rising", "estimated_views_30d": 85000,
         "target_audience": "25-45 year olds building long-term wealth",
         "hook_suggestion": "Most people don't realize their savings account is slowly destroying their wealth.",
         "keywords": ["investing for beginners", "compound interest", "index funds", "wealth building", "passive income"],
         "urgency": "evergreen"},
        {"title": "7 Passive Income Streams That Made Me $8,400 Last Month",
         "content_angle": "Detailed breakdown of each stream with actual income proof",
         "search_volume_tier": "very_high", "competition": "high",
         "monetization_potential": "high", "trend": "stable", "estimated_views_30d": 120000,
         "target_audience": "Millennials seeking financial independence",
         "hook_suggestion": "What if I told you that last month, while I slept, I made more than most people's entire paycheck?",
         "keywords": ["passive income", "multiple income streams", "make money online", "financial freedom", "side hustle"],
         "urgency": "evergreen"},
        {"title": "The $0 Budget Method That Saved Me $14,000 in One Year",
         "content_angle": "Zero-based budgeting adapted for irregular income earners",
         "search_volume_tier": "high", "competition": "low",
         "monetization_potential": "high", "trend": "rising", "estimated_views_30d": 42000,
         "target_audience": "People living paycheck to paycheck wanting a concrete system",
         "hook_suggestion": "I used to think budgeting was about deprivation — until this method changed everything.",
         "keywords": ["zero based budget", "save money fast", "budgeting for beginners", "personal finance", "debt free"],
         "urgency": "evergreen"},
        {"title": "Why Your 401k Is Quietly Underperforming (And What To Do)",
         "content_angle": "Fee analysis + allocation optimization most employers won't explain",
         "search_volume_tier": "high", "competition": "low",
         "monetization_potential": "high", "trend": "rising", "estimated_views_30d": 55000,
         "target_audience": "Employed Americans with workplace retirement accounts",
         "hook_suggestion": "The single fee buried in your 401k plan is costing you six figures over your career.",
         "keywords": ["401k optimization", "retirement planning", "investment fees", "index fund 401k", "retirement mistakes"],
         "urgency": "evergreen"},
    ],
    "tech": [
        {"title": "I Used AI Tools for 30 Days — Honest Productivity Results",
         "content_angle": "Controlled experiment with before/after workflow metrics",
         "search_volume_tier": "very_high", "competition": "medium",
         "monetization_potential": "high", "trend": "viral", "estimated_views_30d": 200000,
         "target_audience": "Knowledge workers and solopreneurs wanting real productivity gains",
         "hook_suggestion": "I replaced 4 hours of my daily work with AI — here's what actually happened.",
         "keywords": ["AI productivity", "ChatGPT workflow", "AI tools 2024", "work smarter", "automation"],
         "urgency": "timely"},
        {"title": "Python Automation Scripts That Saved Me 20 Hours This Week",
         "content_angle": "Real scripts shown line by line with copy-paste GitHub repo",
         "search_volume_tier": "high", "competition": "medium",
         "monetization_potential": "medium", "trend": "rising", "estimated_views_30d": 55000,
         "target_audience": "Developers and technical professionals automating repetitive work",
         "hook_suggestion": "You're wasting time on tasks that a 20-line Python script could handle forever.",
         "keywords": ["python automation", "python scripts", "automate boring stuff", "programming tutorial", "productivity coding"],
         "urgency": "evergreen"},
        {"title": "Build a Full SaaS in 72 Hours With These 5 Tools",
         "content_angle": "No-code/low-code stack for non-technical founders — real product shipped",
         "search_volume_tier": "high", "competition": "low",
         "monetization_potential": "high", "trend": "rising", "estimated_views_30d": 78000,
         "target_audience": "Aspiring founders and developers wanting to validate fast",
         "hook_suggestion": "You no longer need a development team to ship software that customers will pay for.",
         "keywords": ["build saas fast", "no code startup", "saas tutorial", "solopreneur tools", "mvp development"],
         "urgency": "timely"},
    ],
    "health": [
        {"title": "I Ate Like a Longevity Researcher for 60 Days — Blood Work Results",
         "content_angle": "Blue Zone dietary principles tested with actual lab biomarker data",
         "search_volume_tier": "high", "competition": "low",
         "monetization_potential": "high", "trend": "rising", "estimated_views_30d": 68000,
         "target_audience": "Health-conscious adults 35-60 focused on preventive medicine",
         "hook_suggestion": "The world's longest-lived people share one dietary pattern that modern science just confirmed.",
         "keywords": ["longevity diet", "blue zone food", "healthy eating science", "anti-aging diet", "longevity research"],
         "urgency": "timely"},
        {"title": "10-Minute Morning Routine Backed by Neuroscience",
         "content_angle": "Dopamine and cortisol regulation explained with protocol timestamps",
         "search_volume_tier": "very_high", "competition": "high",
         "monetization_potential": "medium", "trend": "stable", "estimated_views_30d": 95000,
         "target_audience": "Professionals struggling with low energy, focus, and motivation",
         "hook_suggestion": "What you do in the first 10 minutes of your morning literally sets your brain chemistry for the day.",
         "keywords": ["morning routine", "morning habits", "productivity neuroscience", "mental health habits", "cortisol morning"],
         "urgency": "evergreen"},
    ],
    "default": [
        {"title": "The Beginner's Guide Experts Don't Want You to See",
         "content_angle": "First-principles breakdown bypassing the gatekeeping jargon",
         "search_volume_tier": "high", "competition": "medium",
         "monetization_potential": "medium", "trend": "stable", "estimated_views_30d": 35000,
         "target_audience": "Complete beginners ready to take the topic seriously",
         "hook_suggestion": "I spent 3 months figuring out what it took experts years to learn — and I'm sharing all of it.",
         "keywords": ["beginner guide", "how to start", "step by step", "complete guide", "for beginners"],
         "urgency": "evergreen"},
        {"title": "5 Mistakes That Cost Me Time, Money, and Credibility",
         "content_angle": "Personal failure story with honest cost analysis and specific fixes",
         "search_volume_tier": "high", "competition": "low",
         "monetization_potential": "high", "trend": "rising", "estimated_views_30d": 48000,
         "target_audience": "Intermediate practitioners who have hit a plateau",
         "hook_suggestion": "If you're doing any of these 5 things, you're already behind — and you might not even know it.",
         "keywords": ["common mistakes", "avoid mistakes", "improve results", "lessons learned", "mistakes beginners make"],
         "urgency": "evergreen"},
        {"title": "What Nobody Tells You When You're Starting Out",
         "content_angle": "Unfiltered insider knowledge from practitioners not influencers",
         "search_volume_tier": "medium", "competition": "low",
         "monetization_potential": "medium", "trend": "rising", "estimated_views_30d": 28000,
         "target_audience": "Motivated beginners who feel overwhelmed by conflicting advice",
         "hook_suggestion": "After talking to hundreds of people who failed at this, I found the pattern nobody talks about.",
         "keywords": ["insider tips", "nobody tells you", "real talk", "honest advice", "truth about"],
         "urgency": "evergreen"},
    ],
}


def _resolve_templates(niche: str) -> list[dict]:
    n = niche.lower()
    for key in _MOCK_TEMPLATES:
        if key in n:
            return _MOCK_TEMPLATES[key]
    return _MOCK_TEMPLATES["default"]


# ── agent ─────────────────────────────────────────────────────────────────────

class ScoutAgent(BaseAgent[ScoutInput, ScoutOutput]):
    agent_name = "scout"
    default_temperature = 0.8

    async def execute(self, inp: ScoutInput) -> ScoutOutput:
        filters = ""
        if inp.keywords_to_exclude:
            filters += f"\nExclude topics containing: {', '.join(inp.keywords_to_exclude)}"
        if inp.keywords_to_include:
            filters += f"\nPrioritize topics around: {', '.join(inp.keywords_to_include)}"

        user = (
            f"Niche: {inp.niche}\n"
            f"Channel: {inp.channel_name}\n"
            f"Scouting window: last {inp.days_back} days\n"
            f"Competitor channels: {', '.join(inp.competitor_channels) or 'none specified'}\n"
            f"Generate exactly {inp.count} ranked opportunities.{filters}\n\n"
            f"Return JSON:\n{_SCHEMA}"
        )
        raw = await self._call_llm(_SYSTEM, user, temperature=0.8, json_mode=True)
        data = self._parse_json(raw)
        return ScoutOutput(
            niche=inp.niche,
            opportunities=[ScoutedOpportunity(**o) for o in data.get("opportunities", [])],
            market_insights=data.get("market_insights", ""),
            recommended_priority=data.get("recommended_priority", []),
            next_refresh_hours=data.get("next_refresh_hours", 48),
        )

    async def mock_execute(self, inp: ScoutInput) -> ScoutOutput:
        rng = random.Random(self._seed(inp.input_hash()))
        templates = _resolve_templates(inp.niche)
        count = min(inp.count, len(templates))

        opportunities: list[ScoutedOpportunity] = []
        for i in range(count):
            tpl = templates[i % len(templates)].copy()
            tpl["estimated_views_30d"] = int(tpl["estimated_views_30d"] * rng.uniform(0.75, 1.25))
            opportunities.append(ScoutedOpportunity(**tpl))

        return ScoutOutput(
            niche=inp.niche,
            opportunities=opportunities,
            market_insights=(
                f"The {inp.niche} niche is showing strong engagement on case-study and how-to formats. "
                "CPM rates are above the platform average, driven by high advertiser competition in the "
                "B2B and financial products categories. Channels publishing 2x per week are outperforming "
                "daily publishers in retention and subscriber conversion this quarter."
            ),
            recommended_priority=[o.title for o in opportunities[:3]],
            next_refresh_hours=rng.choice([24, 48, 72]),
        )

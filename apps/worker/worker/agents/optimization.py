"""
OptimizationAgent — analyses content and returns data-driven improvement recommendations.

Takes current script + analytics context and returns prioritised suggestions,
A/B variants, and predicted metric improvements.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput

# ── schemas ───────────────────────────────────────────────────────────────────

OptimizationGoal = Literal[
    "increase_views", "increase_ctr", "increase_avd",
    "increase_revenue", "grow_subscribers"
]


class OptimizationInput(AgentInput):
    title: str
    script: str
    niche: str
    current_metadata: dict = Field(default_factory=dict)
    analytics: dict = Field(default_factory=dict)
    goals: list[OptimizationGoal] = Field(default_factory=list)
    channel_avg_ctr: float = Field(default=0.05, ge=0.0, le=1.0)
    channel_avg_avd_seconds: int = Field(default=300, ge=0)


class OptimizationSuggestion(BaseModel):
    category: Literal["hook", "pacing", "seo", "cta", "thumbnail", "description", "tags", "title", "structure"]
    priority: Literal["critical", "high", "medium", "low"]
    current: str
    suggested: str
    impact: str
    effort: Literal["easy", "medium", "hard"]
    expected_metric_delta: str


class ABVariant(BaseModel):
    element: str
    variant_a: str
    variant_b: str
    hypothesis: str
    success_metric: str


class OptimizationOutput(AgentOutput):
    overall_score: float = Field(ge=0.0, le=10.0)
    suggestions: list[OptimizationSuggestion]
    priority_actions: list[str]
    predicted_ctr_delta_pct: float
    predicted_avd_delta_pct: float
    ab_variants: list[ABVariant]
    optimization_summary: str
    quick_wins: list[str]


# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """You are a YouTube growth strategist specialising in content performance optimisation.
You analyse scripts, metadata, and analytics to generate data-driven improvement recommendations.

For each suggestion:
- category: hook | pacing | seo | cta | thumbnail | description | tags | title | structure
- priority: critical | high | medium | low
- current: the problematic element (quote directly from content)
- suggested: the improved version (fully written out, ready to use)
- impact: what metric this affects and by how much (estimated)
- effort: easy (< 15 min) | medium (15-60 min) | hard (> 60 min)
- expected_metric_delta: e.g. "+12-18% CTR", "+45s avg view duration"

A/B variants should be for high-impact, easy-to-test elements.
Predicted deltas should be conservative and evidence-based.

Return ONLY valid JSON, no markdown."""

_SCHEMA = """{
  "overall_score": 7.2,
  "suggestions": [
    {
      "category": "hook",
      "priority": "critical",
      "current": "string (existing text)",
      "suggested": "string (improved version)",
      "impact": "string",
      "effort": "easy",
      "expected_metric_delta": "string"
    }
  ],
  "priority_actions": ["action 1", "action 2", "action 3"],
  "predicted_ctr_delta_pct": 15.0,
  "predicted_avd_delta_pct": 8.0,
  "ab_variants": [
    {
      "element": "title",
      "variant_a": "string",
      "variant_b": "string",
      "hypothesis": "string",
      "success_metric": "CTR > 6%"
    }
  ],
  "optimization_summary": "string",
  "quick_wins": ["string"]
}"""

# ── agent ─────────────────────────────────────────────────────────────────────

class OptimizationAgent(BaseAgent[OptimizationInput, OptimizationOutput]):
    agent_name = "optimization"
    default_temperature = 0.3

    async def execute(self, inp: OptimizationInput) -> OptimizationOutput:
        analytics_block = ""
        if inp.analytics:
            analytics_block = (
                f"\n=== ANALYTICS CONTEXT ===\n"
                + "\n".join(f"{k}: {v}" for k, v in inp.analytics.items())
            )

        script_preview = inp.script[:2500] + ("..." if len(inp.script) > 2500 else "")
        user = (
            f"Niche: {inp.niche}\n"
            f"Goals: {', '.join(inp.goals) or 'general optimisation'}\n"
            f"Channel avg CTR: {inp.channel_avg_ctr:.1%}\n"
            f"Channel avg AVD: {inp.channel_avg_avd_seconds}s\n\n"
            f"=== TITLE ===\n{inp.title}\n\n"
            f"=== CURRENT METADATA ===\n"
            + "\n".join(f"{k}: {v}" for k, v in inp.current_metadata.items())
            + f"\n\n=== SCRIPT (preview) ===\n{script_preview}"
            + analytics_block
            + f"\n\nGenerate optimisation report. Return JSON:\n{_SCHEMA}"
        )
        raw = await self._call_llm(_SYSTEM, user, temperature=0.3, json_mode=True)
        data = self._parse_json(raw)
        return self._hydrate(data)

    async def mock_execute(self, inp: OptimizationInput) -> OptimizationOutput:
        rng = random.Random(self._seed(inp.input_hash()))
        script_words = inp.script.split()

        # Analyse the hook (first 100 words)
        hook_preview = " ".join(script_words[:30]) if script_words else inp.title

        suggestions: list[OptimizationSuggestion] = [
            OptimizationSuggestion(
                category="hook",
                priority="critical",
                current=hook_preview[:120],
                suggested=(
                    "Here's a number that most people in this niche never see: "
                    f"{'73%' if rng.random() > 0.5 else '67%'} of people who try the standard approach "
                    "fail within the first 60 days — not because the method is broken, but because nobody "
                    "told them the one thing that actually makes it work. I'll show you that thing today."
                ),
                impact="First 30-second retention — the single largest lever for overall watch time",
                effort="easy",
                expected_metric_delta="+18-25% average view duration",
            ),
            OptimizationSuggestion(
                category="title",
                priority="high",
                current=inp.title,
                suggested=f"The {inp.topic if hasattr(inp, 'topic') else inp.title.split()[0]} System That Changed Everything (Step-by-Step)",
                impact="Search click-through rate and suggested video impressions",
                effort="easy",
                expected_metric_delta="+12-20% CTR from search",
            ),
            OptimizationSuggestion(
                category="seo",
                priority="high",
                current="Primary keyword appears at 45 seconds into script",
                suggested="Move primary keyword to opening sentence — 'In this video, I'll show you exactly how [keyword]...'",
                impact="YouTube's algorithm weights keyword placement in first 60 seconds for indexing",
                effort="easy",
                expected_metric_delta="+8-15% search impressions within 30 days",
            ),
            OptimizationSuggestion(
                category="pacing",
                priority="medium",
                current="Sections 3 and 4 each exceed 3 minutes without a pattern interrupt",
                suggested="Add a micro-cliffhanger at 2:00 mark: 'And there's one more thing about this that almost nobody talks about — I'll get to it in a moment...'",
                impact="Viewer retention at the 40-60% mark of the video",
                effort="easy",
                expected_metric_delta="+30-45s average view duration",
            ),
            OptimizationSuggestion(
                category="cta",
                priority="medium",
                current="Subscribe and turn on notifications",
                suggested=(
                    "If you found this useful, I have a free [niche-specific resource] linked in the description — "
                    "thousands of people have already used it. And if you want the advanced version of this framework, "
                    "the next video covers it in detail — it's right here."
                ),
                impact="Subscribe conversion rate and session watch time",
                effort="easy",
                expected_metric_delta="+5-8% subscriber conversion from viewers",
            ),
            OptimizationSuggestion(
                category="description",
                priority="low",
                current="Description missing chapter timestamps",
                suggested="Add timestamps matching each script section — boosts YouTube chapter generation and search snippet visibility",
                impact="Click-through from search result snippets and in-video chapter navigation",
                effort="easy",
                expected_metric_delta="+6-10% click-through from search snippets",
            ),
        ]

        # Filter to relevant suggestions based on goals
        goal_categories: dict[str, list[str]] = {
            "increase_ctr":       ["title", "thumbnail", "seo"],
            "increase_avd":       ["hook", "pacing", "structure"],
            "increase_views":     ["seo", "title", "tags"],
            "increase_revenue":   ["tags", "description", "cta"],
            "grow_subscribers":   ["cta", "hook"],
        }
        if inp.goals:
            priority_cats = set()
            for g in inp.goals:
                priority_cats.update(goal_categories.get(g, []))
            suggestions.sort(
                key=lambda s: (0 if s.category in priority_cats else 1,
                               ["critical", "high", "medium", "low"].index(s.priority))
            )

        overall_score = round(rng.uniform(6.0, 8.5), 1)
        ctr_delta = round(rng.uniform(10.0, 22.0), 1)
        avd_delta = round(rng.uniform(5.0, 18.0), 1)

        return OptimizationOutput(
            overall_score=overall_score,
            suggestions=suggestions,
            priority_actions=[
                "Rewrite the opening hook to lead with a specific, surprising statistic",
                f"Move the primary keyword into the first sentence of both title and script",
                "Add chapter timestamps to description for search snippet eligibility",
            ],
            predicted_ctr_delta_pct=ctr_delta,
            predicted_avd_delta_pct=avd_delta,
            ab_variants=[
                ABVariant(
                    element="title",
                    variant_a=inp.title,
                    variant_b=f"The {inp.niche.title()} System Nobody's Talking About (Step-by-Step)",
                    hypothesis="Question-format or 'nobody talking about' framing outperforms declarative title",
                    success_metric="CTR > 6% sustained over 500 impressions",
                ),
                ABVariant(
                    element="thumbnail_headline",
                    variant_a="STEP BY STEP",
                    variant_b=f"{rng.randint(3, 9)} STEPS",
                    hypothesis="Specific number outperforms generic 'step by step' in thumbnail text",
                    success_metric="CTR improvement > 10% vs. control",
                ),
            ],
            optimization_summary=(
                f"Content quality score: {overall_score}/10. "
                f"Highest-impact opportunity is the hook — rewriting the first 30 seconds alone is predicted to "
                f"deliver a {avd_delta:.0f}% improvement in average view duration. "
                f"SEO positioning of the primary keyword and chapter timestamp additions are easy wins with "
                f"measurable impact within 30 days of republication."
            ),
            quick_wins=[
                "Add chapter timestamps to description (< 5 minutes)",
                "Move primary keyword to first sentence of script",
                "Change CTA from generic 'subscribe' to specific next-video or resource reference",
            ],
        )

    @staticmethod
    def _hydrate(data: dict) -> OptimizationOutput:
        return OptimizationOutput(
            overall_score=float(data.get("overall_score", 7.0)),
            suggestions=[OptimizationSuggestion(**s) for s in data.get("suggestions", [])],
            priority_actions=data.get("priority_actions", []),
            predicted_ctr_delta_pct=float(data.get("predicted_ctr_delta_pct", 0.0)),
            predicted_avd_delta_pct=float(data.get("predicted_avd_delta_pct", 0.0)),
            ab_variants=[ABVariant(**v) for v in data.get("ab_variants", [])],
            optimization_summary=data.get("optimization_summary", ""),
            quick_wins=data.get("quick_wins", []),
        )

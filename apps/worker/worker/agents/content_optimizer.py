"""
ContentOptimizerAgent — growth brain.

Consumes structured analytics signals (CTR trend, retention curves, watch-time
velocity, top/bottom performer patterns) and produces:
  • content_recommendations  — specific improvements tied to evidence
  • next_topics              — 10 data-driven topics with estimated CTR/retention
  • format_suggestions       — duration, structure, opening type
  • watch_time_insights      — retention patterns and drop-off actions
  • ctr_insights             — thumbnail/title signals from performer spread
  • growth_trajectory        — accelerating | stable | declining | new
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput


# ── input schema ──────────────────────────────────────────────────────────────

class ChannelMetrics(BaseModel):
    total_views: int = 0
    avg_ctr: float = 0.0
    avg_retention_pct: float = 0.0
    total_watch_time_hours: float = 0.0
    avg_rpm: float = 0.0
    total_revenue_usd: float = 0.0
    net_subscribers: int = 0


class PublicationMetricRow(BaseModel):
    title: str
    views: int
    ctr: float
    retention_pct: float
    watch_time_hours: float
    revenue_usd: float
    perf_score: float
    duration_seconds: int = 0


class FormatPerformanceRow(BaseModel):
    duration_bucket: Literal["short", "medium", "long"]  # <5m, 5-15m, >15m
    video_count: int
    avg_views: float
    avg_ctr: float
    avg_retention_pct: float
    avg_watch_time_hours: float


class OptimizationInput(AgentInput):
    channel_name: str
    niche: str
    period_days: int = 28

    # Period aggregates
    metrics: ChannelMetrics = Field(default_factory=ChannelMetrics)

    # Trend signals (positive = improving)
    ctr_trend_pct: float = 0.0          # % change vs prior period
    watch_time_trend_pct: float = 0.0
    views_trend_pct: float = 0.0
    retention_trend_pct: float = 0.0

    top_publications: list[PublicationMetricRow] = Field(default_factory=list)
    bottom_publications: list[PublicationMetricRow] = Field(default_factory=list)
    format_performance: list[FormatPerformanceRow] = Field(default_factory=list)
    existing_topic_titles: list[str] = Field(default_factory=list)


# ── output schema ─────────────────────────────────────────────────────────────

class ContentRecommendation(BaseModel):
    priority: Literal["critical", "high", "medium", "low"]
    rec_type: Literal[
        "improve_thumbnail", "improve_hook", "optimize_title",
        "change_format", "increase_cadence", "repeat_format",
        "scale_topic", "kill_topic", "localize",
    ]
    title: str
    body: str
    metric_key: str | None = None
    metric_current: float | None = None
    metric_target: float | None = None
    impact_label: str | None = None
    evidence: str


class NextTopic(BaseModel):
    title: str
    rationale: str
    urgency: Literal["high", "medium", "low"]
    estimated_ctr: float = Field(ge=0.0, le=20.0)
    estimated_retention_pct: float = Field(ge=0.0, le=100.0)
    estimated_views: int
    keyword_angle: str


class FormatSuggestion(BaseModel):
    format_label: str
    duration_range_seconds: tuple[int, int]
    opening_style: str
    structure: str
    rationale: str
    evidence: str
    expected_retention_lift_pct: float


class WatchTimeInsight(BaseModel):
    pattern: str
    impact: str
    action: str
    priority: Literal["critical", "high", "medium", "low"]


class CTRInsight(BaseModel):
    pattern: str
    evidence: str
    action: str
    expected_ctr_lift_pct: float


class OptimizationOutput(AgentOutput):
    growth_trajectory: Literal["accelerating", "stable", "declining", "new"]
    growth_score: float = Field(ge=0.0, le=100.0)
    summary: str
    content_recommendations: list[ContentRecommendation] = Field(default_factory=list)
    next_topics: list[NextTopic] = Field(default_factory=list)
    format_suggestions: list[FormatSuggestion] = Field(default_factory=list)
    watch_time_insights: list[WatchTimeInsight] = Field(default_factory=list)
    ctr_insights: list[CTRInsight] = Field(default_factory=list)
    top_performer_patterns: list[str] = Field(default_factory=list)


# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """You are the growth brain for a faceless YouTube channel automation platform.

You receive structured analytics signals and produce a comprehensive optimization report.
Your outputs drive real content decisions — be specific, evidence-based, and ruthlessly prioritized.

Rules:
- All topics: no faces, no people — abstract, data-driven, educational niche content
- CTR benchmark: 4.0% (great), 2.5% (acceptable), <1.5% = critical failure
- Retention benchmark: 40% of video duration (great), 25% (floor), <20% = critical
- Watch time: key monetization signal — optimise for total minutes, not just views
- format labels must be human-readable (e.g. "8-min listicle", "12-min deep dive")
- evidence must reference actual input metrics, not generic advice
- growth_score: 0–100. 50 = stable. >70 = accelerating. <35 = declining.
- Return ONLY valid JSON. No markdown, no preamble."""

_SCHEMA = """{
  "growth_trajectory": "accelerating|stable|declining|new",
  "growth_score": 62.5,
  "summary": "2-3 sentence channel health summary with specific numbers",
  "content_recommendations": [
    {
      "priority": "critical|high|medium|low",
      "rec_type": "improve_thumbnail|improve_hook|optimize_title|change_format|increase_cadence|repeat_format|scale_topic|kill_topic|localize",
      "title": "Concise action title",
      "body": "Detailed actionable body with specific steps",
      "metric_key": "ctr|retention_pct|watch_time_hours|views",
      "metric_current": 1.8,
      "metric_target": 4.0,
      "impact_label": "+25% clicks",
      "evidence": "Specific metric data from input that justifies this rec"
    }
  ],
  "next_topics": [
    {
      "title": "Topic title (not a question)",
      "rationale": "Why this topic, based on channel performance patterns",
      "urgency": "high|medium|low",
      "estimated_ctr": 4.2,
      "estimated_retention_pct": 38.0,
      "estimated_views": 15000,
      "keyword_angle": "specific long-tail angle"
    }
  ],
  "format_suggestions": [
    {
      "format_label": "10-min step-by-step guide",
      "duration_range_seconds": [540, 660],
      "opening_style": "Counterintuitive statement + promise in first 15 seconds",
      "structure": "Hook 0-30s → 3-step framework with timestamps → CTA at 80%",
      "rationale": "Why this format based on analytics",
      "evidence": "Specific evidence from top performers or format analysis",
      "expected_retention_lift_pct": 12.5
    }
  ],
  "watch_time_insights": [
    {
      "pattern": "Observed watch time pattern",
      "impact": "What this means for monetization",
      "action": "Specific action to take",
      "priority": "critical|high|medium|low"
    }
  ],
  "ctr_insights": [
    {
      "pattern": "Observed CTR pattern",
      "evidence": "Data supporting this",
      "action": "Specific thumbnail or title change",
      "expected_ctr_lift_pct": 15.0
    }
  ],
  "top_performer_patterns": [
    "Pattern observed across top performing videos"
  ]
}"""


# ── agent ─────────────────────────────────────────────────────────────────────

class ContentOptimizerAgent(BaseAgent[OptimizationInput, OptimizationOutput]):
    agent_name = "content_optimizer"
    default_temperature = 0.6

    async def execute(self, inp: OptimizationInput) -> OptimizationOutput:
        user = self._build_prompt(inp)
        raw = await self._call_llm(_SYSTEM, user, temperature=0.6, json_mode=True)
        data = self._parse_json(raw)
        return self._hydrate(data)

    async def mock_execute(self, inp: OptimizationInput) -> OptimizationOutput:
        m = inp.metrics
        ctr_ok = m.avg_ctr >= 0.025
        ret_ok = m.avg_retention_pct >= 0.25

        if inp.watch_time_trend_pct > 10:
            trajectory = "accelerating"
            growth_score = 72.0
        elif inp.watch_time_trend_pct < -10:
            trajectory = "declining"
            growth_score = 32.0
        elif m.total_views == 0:
            trajectory = "new"
            growth_score = 50.0
        else:
            trajectory = "stable"
            growth_score = 55.0

        recs: list[ContentRecommendation] = []
        if not ctr_ok and m.avg_ctr > 0:
            recs.append(ContentRecommendation(
                priority="critical" if m.avg_ctr < 0.015 else "high",
                rec_type="improve_thumbnail",
                title=f"CTR {m.avg_ctr*100:.1f}% — thumbnail redesign required",
                body=(
                    f"Channel CTR is {m.avg_ctr*100:.1f}%, below the {2.5 if m.avg_ctr >= 0.015 else 1.5}% threshold. "
                    "Switch to bold-text-only thumbnails with max 4 words. "
                    "Test yellow/white text on dark background — highest contrast at 168×94px mobile."
                ),
                metric_key="ctr",
                metric_current=round(m.avg_ctr * 100, 2),
                metric_target=4.0,
                impact_label="+15–30% clicks",
                evidence=f"Channel avg CTR {m.avg_ctr*100:.1f}% vs 4% benchmark over {inp.period_days}d",
            ))
        if not ret_ok and m.avg_retention_pct > 0:
            recs.append(ContentRecommendation(
                priority="high",
                rec_type="improve_hook",
                title=f"Retention {m.avg_retention_pct*100:.0f}% — hook needs rewrite",
                body=(
                    f"Avg retention {m.avg_retention_pct*100:.0f}% is below the 25% floor. "
                    "Open every video with the most counterintuitive fact you cover. "
                    "Cut all intros, logos, and music to < 2 seconds."
                ),
                metric_key="retention_pct",
                metric_current=round(m.avg_retention_pct * 100, 1),
                metric_target=40.0,
                impact_label="+10–20% watch time",
                evidence=f"Channel avg retention {m.avg_retention_pct*100:.0f}% over {inp.period_days}d",
            ))
        if inp.views_trend_pct > 0 and m.total_views > 0:
            recs.append(ContentRecommendation(
                priority="medium",
                rec_type="increase_cadence",
                title="Views trending up — increase upload frequency",
                body=(
                    f"Views grew {inp.views_trend_pct:+.0f}% vs prior period. "
                    "Algorithm favours channels with consistent cadence. "
                    "Aim for at least 2 videos/week to ride this momentum window."
                ),
                metric_key="views_trend_pct",
                metric_current=round(inp.views_trend_pct, 1),
                metric_target=20.0,
                impact_label="+20–40% impressions",
                evidence=f"Views trend: {inp.views_trend_pct:+.0f}%",
            ))

        top_5 = inp.top_publications[:5]
        next_topics: list[NextTopic] = []
        base_ctr = max(m.avg_ctr * 1.15, 0.03)
        base_ret = max(m.avg_retention_pct * 1.1, 0.30)
        topic_seeds = [
            ("Top 10 Mistakes in {niche}", "number-list format drives high CTR"),
            ("How Much Money {niche} Makes in 2025", "income reveal = high curiosity gap"),
            ("I Tested Every {niche} Strategy", "experiment format = top retention"),
            ("The Truth About {niche} No One Tells You", "contrarian hook outperforms"),
            ("Complete {niche} Roadmap for Beginners", "long-form guide = high watch time"),
            ("{niche} vs {niche}: Which Is Better?", "comparison format = algorithm favoured"),
            ("Why 90% of {niche} Fails (And How to Win)", "pain-point open = high retention"),
            ("I Went From 0 to $X in {niche}", "transformation arc = high completion"),
            ("The {niche} Playbook That Actually Works", "authority positioning"),
            ("Hidden {niche} Opportunities You're Missing", "FOMO frame = high CTR"),
        ]
        niche_word = inp.niche.split()[0] if inp.niche else "this niche"
        existing_lower = {t.lower() for t in inp.existing_topic_titles}
        for seed, rationale in topic_seeds:
            title = seed.replace("{niche}", niche_word)
            if any(niche_word.lower() in t for t in existing_lower):
                pass
            next_topics.append(NextTopic(
                title=title,
                rationale=f"{rationale}. Based on {inp.channel_name} top performers: avg CTR {m.avg_ctr*100:.1f}%.",
                urgency="high" if len(next_topics) < 3 else "medium",
                estimated_ctr=round(base_ctr * 100 * (1 + len(next_topics) * 0.02), 1),
                estimated_retention_pct=round(base_ret * 100 * 0.98 ** len(next_topics), 1),
                estimated_views=max(int(m.total_views / max(len(inp.top_publications), 1) * 0.8), 1000),
                keyword_angle=f"{niche_word} {['guide 2025', 'tutorial', 'strategies', 'tips', 'mistakes'][len(next_topics) % 5]}",
            ))
            if len(next_topics) >= 10:
                break

        format_suggestions: list[FormatSuggestion] = []
        best_format = max(inp.format_performance, key=lambda f: f.avg_views, default=None)
        if best_format:
            format_suggestions.append(FormatSuggestion(
                format_label=f"{best_format.duration_bucket.replace('short','5-8 min').replace('medium','8-15 min').replace('long','15-25 min')} listicle",
                duration_range_seconds={"short": (240, 480), "medium": (480, 900), "long": (900, 1500)}[best_format.duration_bucket],
                opening_style="Counterintuitive statement that promises transformation in first 20 seconds",
                structure="Hook 0-30s → numbered steps with timestamps → tight CTA at 85% mark",
                rationale=f"'{best_format.duration_bucket}' format averages {best_format.avg_views:.0f} views vs channel avg",
                evidence=f"{best_format.video_count} videos in this bucket: avg CTR {best_format.avg_ctr*100:.1f}%, retention {best_format.avg_retention_pct*100:.0f}%",
                expected_retention_lift_pct=8.0,
            ))
        else:
            format_suggestions.append(FormatSuggestion(
                format_label="8-12 min educational listicle",
                duration_range_seconds=(480, 720),
                opening_style="Counterintuitive statement in first 15 seconds",
                structure="Hook 0-30s → 5-7 numbered items with timestamps → CTA",
                rationale="Listicle format has proven CTR lift for faceless educational channels",
                evidence="Industry benchmark: 4-8% CTR for this format vs 2-3% average",
                expected_retention_lift_pct=10.0,
            ))

        wt_insights: list[WatchTimeInsight] = []
        if inp.watch_time_trend_pct < -5:
            wt_insights.append(WatchTimeInsight(
                pattern=f"Watch time declining {inp.watch_time_trend_pct:.0f}% vs prior period",
                impact="Fewer minutes served = algorithm reduces distribution",
                action="Add chapter markers, cut dead air, restructure to place best content at 60% mark",
                priority="critical",
            ))
        elif inp.watch_time_trend_pct > 10:
            wt_insights.append(WatchTimeInsight(
                pattern=f"Watch time growing {inp.watch_time_trend_pct:+.0f}%",
                impact="Algorithm is increasing impressions — now is the time to post more",
                action="Double upload frequency for 4 weeks while growth window is open",
                priority="high",
            ))

        ctr_insights: list[CTRInsight] = []
        if top_5 and m.avg_ctr > 0:
            top_ctr = sum(p.ctr for p in top_5) / len(top_5)
            if top_ctr > m.avg_ctr * 1.3:
                ctr_insights.append(CTRInsight(
                    pattern=f"Top 5 videos average {top_ctr*100:.1f}% CTR vs channel avg {m.avg_ctr*100:.1f}%",
                    evidence=", ".join(f'"{p.title[:40]}"' for p in top_5[:3]),
                    action="Study thumbnail patterns from top performers: extract dominant color, text length, visual subject. Apply across all upcoming videos.",
                    expected_ctr_lift_pct=round((top_ctr / m.avg_ctr - 1) * 50, 1),
                ))

        top_patterns = []
        if top_5:
            top_patterns.append(f"Top videos avg {sum(p.views for p in top_5)//len(top_5):,} views, {sum(p.ctr for p in top_5)/len(top_5)*100:.1f}% CTR")
        if inp.format_performance:
            best = max(inp.format_performance, key=lambda f: f.avg_retention_pct)
            top_patterns.append(f"{best.duration_bucket.capitalize()} format ({best.duration_bucket.replace('short','<5min').replace('medium','5-15min').replace('long','>15min')}) has highest retention: {best.avg_retention_pct*100:.0f}%")
        top_patterns.append("Consistent upload schedule increases algorithmic impressions by 15-25%")

        return OptimizationOutput(
            growth_trajectory=trajectory,
            growth_score=growth_score,
            summary=(
                f"{inp.channel_name} is in {trajectory} phase. "
                f"CTR: {m.avg_ctr*100:.1f}%, retention: {m.avg_retention_pct*100:.0f}%, "
                f"watch time trend: {inp.watch_time_trend_pct:+.0f}%. "
                f"Priority: {'thumbnail redesign' if not ctr_ok else 'scale winning formats'}."
            ),
            content_recommendations=recs,
            next_topics=next_topics,
            format_suggestions=format_suggestions,
            watch_time_insights=wt_insights,
            ctr_insights=ctr_insights,
            top_performer_patterns=top_patterns,
        )

    def _build_prompt(self, inp: OptimizationInput) -> str:
        m = inp.metrics
        top_block = "\n".join(
            f"  {i+1}. '{p.title[:60]}' — {p.views:,}v, CTR {p.ctr*100:.1f}%, ret {p.retention_pct*100:.0f}%, score {p.perf_score:.0f}"
            for i, p in enumerate(inp.top_publications[:5])
        ) or "  (no data)"
        bot_block = "\n".join(
            f"  {i+1}. '{p.title[:60]}' — {p.views:,}v, CTR {p.ctr*100:.1f}%, ret {p.retention_pct*100:.0f}%, score {p.perf_score:.0f}"
            for i, p in enumerate(inp.bottom_publications[:5])
        ) or "  (no data)"
        fmt_block = "\n".join(
            f"  {f.duration_bucket} ({f.video_count} vids): avg {f.avg_views:.0f}v, CTR {f.avg_ctr*100:.1f}%, ret {f.avg_retention_pct*100:.0f}%"
            for f in inp.format_performance
        ) or "  (no data)"
        topics_block = "\n".join(f"  - {t}" for t in inp.existing_topic_titles[:20]) or "  (none)"

        return f"""Channel: {inp.channel_name}
Niche: {inp.niche}
Period: last {inp.period_days} days

=== CHANNEL METRICS ===
Views: {m.total_views:,}  |  CTR: {m.avg_ctr*100:.2f}%  |  Retention: {m.avg_retention_pct*100:.1f}%
Watch time: {m.total_watch_time_hours:.0f}h  |  RPM: ${m.avg_rpm:.2f}  |  Revenue: ${m.total_revenue_usd:.2f}
Net subscribers: {m.net_subscribers:+,}

=== TREND vs PRIOR PERIOD ===
CTR trend: {inp.ctr_trend_pct:+.1f}%
Watch time trend: {inp.watch_time_trend_pct:+.1f}%
Views trend: {inp.views_trend_pct:+.1f}%
Retention trend: {inp.retention_trend_pct:+.1f}%

=== TOP 5 VIDEOS ===
{top_block}

=== BOTTOM 5 VIDEOS ===
{bot_block}

=== FORMAT PERFORMANCE ===
{fmt_block}

=== EXISTING TOPICS IN PIPELINE ===
{topics_block}

Generate a comprehensive optimization report. Return JSON:
{_SCHEMA}"""

    @staticmethod
    def _hydrate(data: dict) -> OptimizationOutput:
        return OptimizationOutput(
            growth_trajectory=data.get("growth_trajectory", "stable"),
            growth_score=float(data.get("growth_score", 50.0)),
            summary=data.get("summary", ""),
            content_recommendations=[
                ContentRecommendation(**r) for r in data.get("content_recommendations", [])
            ],
            next_topics=[
                NextTopic(**t) for t in data.get("next_topics", [])
            ],
            format_suggestions=[
                FormatSuggestion(**f) for f in data.get("format_suggestions", [])
            ],
            watch_time_insights=[
                WatchTimeInsight(**w) for w in data.get("watch_time_insights", [])
            ],
            ctr_insights=[
                CTRInsight(**c) for c in data.get("ctr_insights", [])
            ],
            top_performer_patterns=data.get("top_performer_patterns", []),
        )

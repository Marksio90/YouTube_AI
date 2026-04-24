"""
ScoringService — performance scoring, rankings, and rule-based recommendations.

Scoring model
─────────────
Each metric is normalised to 0–100 relative to a benchmark, then
clamped and combined with fixed weights:

  dimension       weight  benchmark
  ─────────────── ──────  ──────────────────────────────────────────
  view_score       0.30   channel median views (or 1 000 for pubs)
  ctr_score        0.25   4.0 % CTR
  retention_score  0.25   40 % of video duration watched
  revenue_score    0.10   $2.50 RPM
  growth_score     0.10   0.2 % of viewers subscribe

composite = Σ(weight × dimension_score)   range: 0–100

Rankings
────────
- publication rank in channel  (1 = best)
- channel rank across all owner channels

Rule recommendations
────────────────────
  improve_thumbnail  CTR < 2.5 % on ≥ 500 impressions  → priority high/critical
  improve_hook       retention < 25 % on ≥ 500 views    → priority high
  repeat_format      publication score ≥ 80              → priority medium
  kill_topic         ≥ 3 pubs on topic, all score < 30   → priority medium
  scale_topic        ≥ 1 high-scorer on topic, < 3 pubs  → priority high
  localize           RPM ≥ $5 + views ≥ 3 000           → priority low
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics import AnalyticsSnapshot, SnapshotType
from app.db.models.channel import Channel
from app.db.models.performance import (
    Recommendation,
    RecommendationPriority,
    RecommendationSource,
    RecommendationStatus,
    RecommendationType,
    PerformanceScore,
)
from app.db.models.publication import Publication
from app.db.models.topic import Topic
from app.schemas.analytics import (
    ChannelRankEntry,
    ChannelRankingResponse,
    PerformanceScoreRead,
    RecommendationRead,
    TopicRankEntry,
    TopicRankingResponse,
)

log = structlog.get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_BENCHMARKS = {
    "ctr":       0.04,    # 4 % CTR = score 100
    "retention": 0.40,    # 40 % retention = score 100
    "rpm":       2.50,    # $2.50 RPM = score 100
    "sub_rate":  0.002,   # 0.2 % subscriber rate = score 100
}

_WEIGHTS = {
    "view":      0.30,
    "ctr":       0.25,
    "retention": 0.25,
    "revenue":   0.10,
    "growth":    0.10,
}

# Rule thresholds
_CTR_CRITICAL = 0.015     # < 1.5 % = critical
_CTR_HIGH     = 0.025     # < 2.5 % = high
_RETENTION_LOW = 0.25     # < 25 % = low retention
_MIN_IMPRESSIONS = 500
_MIN_VIEWS = 500
_HIGH_RPM = 5.0
_HIGH_VIEWS_FOR_LOCALIZE = 3_000
_SCORE_REPEAT = 80.0      # score ≥ 80 → repeat format
_SCORE_KILL   = 30.0      # score < 30 → kill candidate


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _norm(value: float, benchmark: float) -> float:
    """Normalise value to 0–100 against a benchmark. 2× benchmark = 100."""
    if benchmark <= 0:
        return 0.0
    return _clamp((value / benchmark) * 50.0)


def _compute_composite(
    *,
    views: int,
    channel_median_views: float,
    ctr: float,
    retention_pct: float,
    rpm: float,
    subs_net: int,
) -> dict[str, float]:
    view_score      = _norm(views, channel_median_views * 2) if channel_median_views > 0 else _norm(views, 1000)
    ctr_score       = _norm(ctr, _BENCHMARKS["ctr"])
    retention_score = _norm(retention_pct, _BENCHMARKS["retention"])
    revenue_score   = _norm(rpm, _BENCHMARKS["rpm"])
    sub_rate        = subs_net / views if views > 0 else 0.0
    growth_score    = _norm(sub_rate, _BENCHMARKS["sub_rate"])

    composite = (
        _WEIGHTS["view"]      * view_score
        + _WEIGHTS["ctr"]       * ctr_score
        + _WEIGHTS["retention"] * retention_score
        + _WEIGHTS["revenue"]   * revenue_score
        + _WEIGHTS["growth"]    * growth_score
    )
    return {
        "score":           _clamp(composite),
        "view_score":      view_score,
        "ctr_score":       ctr_score,
        "retention_score": retention_score,
        "revenue_score":   revenue_score,
        "growth_score":    growth_score,
    }


# ── Service ───────────────────────────────────────────────────────────────────

class ScoringService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Score: publication ────────────────────────────────────────────────────

    async def score_publication(
        self,
        publication_id: uuid.UUID,
        *,
        channel_id: uuid.UUID,
        period_days: int = 28,
    ) -> PerformanceScore:
        date_to   = date.today()
        date_from = date_to - timedelta(days=period_days - 1)

        agg = await self._aggregate_publication(publication_id, date_from, date_to)
        channel_median = await self._channel_median_views(channel_id, period_days)

        dims = _compute_composite(
            views=int(agg["views"]),
            channel_median_views=channel_median,
            ctr=float(agg["ctr"]),
            retention_pct=float(agg["retention_pct"]),
            rpm=float(agg["rpm"]),
            subs_net=0,
        )

        score = await self._upsert_score(
            channel_id=channel_id,
            publication_id=publication_id,
            period_days=period_days,
            dims=dims,
            raw={
                "raw_views":    int(agg["views"]),
                "raw_ctr":      float(agg["ctr"]),
                "raw_retention": float(agg["retention_pct"]),
                "raw_rpm":      float(agg["rpm"]),
                "raw_revenue":  float(agg["revenue"]),
                "raw_subs_net": 0,
            },
        )
        await self._rank_publications(channel_id, period_days)
        return score

    # ── Score: channel ────────────────────────────────────────────────────────

    async def score_channel(
        self,
        channel_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        period_days: int = 28,
    ) -> PerformanceScore:
        date_to   = date.today()
        date_from = date_to - timedelta(days=period_days - 1)

        agg = await self._aggregate_channel(channel_id, date_from, date_to)
        channel_median = await self._channel_median_views(channel_id, period_days)

        dims = _compute_composite(
            views=int(agg["views"]),
            channel_median_views=channel_median,
            ctr=float(agg["ctr"]),
            retention_pct=float(agg["retention_pct"]),
            rpm=float(agg["rpm"]),
            subs_net=int(agg["subs_net"]),
        )

        score = await self._upsert_score(
            channel_id=channel_id,
            publication_id=None,
            period_days=period_days,
            dims=dims,
            raw={
                "raw_views":    int(agg["views"]),
                "raw_ctr":      float(agg["ctr"]),
                "raw_retention": float(agg["retention_pct"]),
                "raw_rpm":      float(agg["rpm"]),
                "raw_revenue":  float(agg["revenue"]),
                "raw_subs_net": int(agg["subs_net"]),
            },
        )
        await self._rank_channels(owner_id, period_days)
        return score

    # ── Rankings ─────────────────────────────────────────────────────────────

    async def topic_ranking(
        self, owner_id: uuid.UUID, period_days: int = 28
    ) -> TopicRankingResponse:
        rows = await self.db.execute(
            text("""
                WITH pub_scores AS (
                    SELECT
                        p.id          AS pub_id,
                        p.channel_id,
                        ps.score      AS perf_score,
                        p.view_count,
                        p.revenue_usd
                    FROM publications p
                    JOIN channels c ON c.id = p.channel_id AND c.owner_id = :owner_id
                    LEFT JOIN performance_scores ps ON ps.publication_id = p.id
                                                   AND ps.period_days = :period
                    WHERE p.status = 'published'
                ),
                topic_pubs AS (
                    SELECT
                        t.id          AS topic_id,
                        t.title       AS topic_title,
                        t.trend_score,
                        COUNT(p.id)   AS pub_count,
                        AVG(p.view_count)              AS avg_views,
                        AVG(COALESCE(ps.score, 0))     AS avg_perf,
                        SUM(p.revenue_usd)             AS total_rev
                    FROM topics t
                    JOIN channels c ON c.id = t.channel_id AND c.owner_id = :owner_id
                    LEFT JOIN publications p ON p.channel_id = t.channel_id
                        AND (
                            p.brief_id IN (SELECT id FROM briefs WHERE topic_id = t.id)
                        )
                    LEFT JOIN performance_scores ps ON ps.publication_id = p.id
                                                   AND ps.period_days = :period
                    WHERE t.status NOT IN ('rejected', 'archived')
                    GROUP BY t.id, t.title, t.trend_score
                )
                SELECT
                    topic_id,
                    topic_title,
                    trend_score,
                    pub_count,
                    COALESCE(avg_views, 0)  AS avg_views,
                    COALESCE(avg_perf, 0)   AS avg_perf,
                    COALESCE(total_rev, 0)  AS total_rev
                FROM topic_pubs
                ORDER BY
                    (COALESCE(avg_perf, 0) * 0.5 + COALESCE(trend_score, 5) * 5) DESC
                LIMIT 50
            """),
            {"owner_id": str(owner_id), "period": period_days},
        )
        entries = []
        for row in rows.mappings():
            avg_perf = float(row["avg_perf"])
            pub_count = int(row["pub_count"] or 0)
            rec: str
            if avg_perf < _SCORE_KILL and pub_count >= 3:
                rec = "kill"
            elif avg_perf >= _SCORE_REPEAT and pub_count < 3:
                rec = "pursue"
            elif avg_perf >= 60:
                rec = "consider"
            else:
                rec = "monitor"

            composite = avg_perf * 0.5 + float(row["trend_score"] or 5) * 5
            entries.append(TopicRankEntry(
                topic_id=uuid.UUID(str(row["topic_id"])),
                title=str(row["topic_title"]),
                score=round(_clamp(composite), 1),
                trend_score=float(row["trend_score"]) if row["trend_score"] is not None else None,
                publication_count=pub_count,
                avg_views=float(row["avg_views"]),
                avg_perf_score=round(avg_perf, 1),
                total_revenue=float(row["total_rev"]),
                recommendation=rec,
            ))
        return TopicRankingResponse(period_days=period_days, entries=entries)

    async def channel_ranking(
        self, owner_id: uuid.UUID, period_days: int = 28
    ) -> ChannelRankingResponse:
        rows = await self.db.execute(
            text("""
                SELECT
                    c.id,
                    c.name,
                    c.niche,
                    COALESCE(ps.score, 0)              AS score,
                    COALESCE(ps.raw_views, 0)          AS total_views,
                    COALESCE(ps.raw_revenue, 0)        AS total_revenue,
                    COALESCE(ps.raw_ctr, 0)            AS avg_ctr,
                    COALESCE(ps.raw_subs_net, 0)       AS net_subscribers,
                    COALESCE(ps.rank_overall, 99999)   AS rank
                FROM channels c
                LEFT JOIN performance_scores ps ON ps.channel_id = c.id
                    AND ps.publication_id IS NULL
                    AND ps.period_days = :period
                WHERE c.owner_id = :owner_id
                ORDER BY score DESC
            """),
            {"owner_id": str(owner_id), "period": period_days},
        )
        entries = [
            ChannelRankEntry(
                channel_id=uuid.UUID(str(r["id"])),
                name=r["name"],
                niche=r["niche"],
                score=round(float(r["score"]), 1),
                rank=i + 1,
                total_views=int(r["total_views"]),
                total_revenue=float(r["total_revenue"]),
                avg_ctr=float(r["avg_ctr"]),
                net_subscribers=int(r["net_subscribers"]),
            )
            for i, r in enumerate(rows.mappings())
        ]
        return ChannelRankingResponse(period_days=period_days, entries=entries)

    # ── Rule-based recommendations ────────────────────────────────────────────

    async def generate_recommendations(
        self,
        channel_id: uuid.UUID,
        *,
        period_days: int = 28,
        replace_existing: bool = True,
    ) -> list[Recommendation]:
        if replace_existing:
            await self.db.execute(
                text("""
                    DELETE FROM recommendations
                    WHERE channel_id = :cid
                      AND source = 'rule'
                      AND status = 'pending'
                """),
                {"cid": str(channel_id)},
            )

        recs: list[Recommendation] = []
        date_to   = date.today()
        date_from = date_to - timedelta(days=period_days - 1)

        # Fetch publications + their aggregated metrics for the period
        pub_rows = await self.db.execute(
            text("""
                SELECT
                    p.id              AS pub_id,
                    p.title           AS pub_title,
                    p.brief_id,
                    b.topic_id,
                    COALESCE(SUM(s.impressions), 0)            AS impressions,
                    COALESCE(SUM(s.views), 0)                  AS views,
                    COALESCE(AVG(s.ctr), 0)                    AS ctr,
                    COALESCE(AVG(s.avg_view_duration_seconds / NULLIF(600, 0)), 0) AS retention_pct,
                    COALESCE(AVG(s.rpm), 0)                    AS rpm,
                    COALESCE(SUM(s.revenue_usd), 0)            AS revenue,
                    COALESCE(ps.score, 0)                      AS perf_score
                FROM publications p
                LEFT JOIN briefs b ON b.id = p.brief_id
                LEFT JOIN analytics_snapshots s ON s.publication_id = p.id
                    AND s.snapshot_date BETWEEN :from_ AND :to_
                    AND s.snapshot_type = 'publication'
                LEFT JOIN performance_scores ps ON ps.publication_id = p.id
                    AND ps.period_days = :period
                WHERE p.channel_id = :cid AND p.status = 'published'
                GROUP BY p.id, p.title, p.brief_id, b.topic_id, ps.score
            """),
            {
                "cid": str(channel_id),
                "from_": date_from.isoformat(),
                "to_": date_to.isoformat(),
                "period": period_days,
            },
        )
        pubs = list(pub_rows.mappings())

        # Group by topic for kill/scale checks
        topic_pubs: dict[str, list[dict]] = {}
        for p in pubs:
            if p["topic_id"]:
                tid = str(p["topic_id"])
                topic_pubs.setdefault(tid, []).append(dict(p))

        expires = datetime.now(tz=timezone.utc) + timedelta(days=14)

        for p in pubs:
            imp   = float(p["impressions"])
            views = float(p["views"])
            ctr   = float(p["ctr"])
            ret   = float(p["retention_pct"])
            rpm   = float(p["rpm"])
            score = float(p["perf_score"])
            pub_id = uuid.UUID(str(p["pub_id"]))

            # ── improve_thumbnail ─────────────────────────────────────────────
            if imp >= _MIN_IMPRESSIONS:
                if ctr < _CTR_CRITICAL:
                    recs.append(self._make_rec(
                        channel_id=channel_id, publication_id=pub_id,
                        rec_type=RecommendationType.improve_thumbnail,
                        priority=RecommendationPriority.critical,
                        title=f"Critical: low CTR on "{p['pub_title'][:60]}"",
                        body=(
                            f"CTR is **{ctr*100:.1f}%** against {_MIN_IMPRESSIONS:,} impressions. "
                            "Benchmark: 4%. Your thumbnail is failing to convert impressions to clicks. "
                            "Replace with a high-contrast, single-subject design. "
                            "Test a bold text overlay (≤ 4 words) that creates curiosity."
                        ),
                        rationale=f"CTR {ctr*100:.1f}% is critically below the 2.5% threshold.",
                        metric_key="ctr",
                        metric_current=round(ctr * 100, 2),
                        metric_target=4.0,
                        impact_label="+15–40% clicks",
                        expires_at=expires,
                    ))
                elif ctr < _CTR_HIGH:
                    recs.append(self._make_rec(
                        channel_id=channel_id, publication_id=pub_id,
                        rec_type=RecommendationType.improve_thumbnail,
                        priority=RecommendationPriority.high,
                        title=f"Low CTR: "{p['pub_title'][:60]}"",
                        body=(
                            f"CTR is **{ctr*100:.1f}%** — below the 2.5% action threshold. "
                            "Consider A/B testing a new thumbnail with a different emotion or "
                            "composition. Add contrasting background color to improve shelf visibility."
                        ),
                        rationale=f"CTR {ctr*100:.1f}% below 2.5% high-priority threshold.",
                        metric_key="ctr",
                        metric_current=round(ctr * 100, 2),
                        metric_target=2.5,
                        impact_label="+8–20% clicks",
                        expires_at=expires,
                    ))

            # ── improve_hook ──────────────────────────────────────────────────
            if views >= _MIN_VIEWS and ret < _RETENTION_LOW:
                recs.append(self._make_rec(
                    channel_id=channel_id, publication_id=pub_id,
                    rec_type=RecommendationType.improve_hook,
                    priority=RecommendationPriority.high,
                    title=f"Weak hook: "{p['pub_title'][:60]}"",
                    body=(
                        f"Average retention is **{ret*100:.0f}%** — viewers are dropping off early. "
                        "The first 30 seconds must promise the payoff immediately. "
                        "Open with the most surprising or counterintuitive fact from your video. "
                        "Cut any intro music longer than 2 seconds."
                    ),
                    rationale=f"Retention {ret*100:.0f}% below 25% threshold on {int(views):,} views.",
                    metric_key="retention_pct",
                    metric_current=round(ret * 100, 1),
                    metric_target=40.0,
                    impact_label="+10–25% watch time",
                    expires_at=expires,
                ))

            # ── repeat_format ─────────────────────────────────────────────────
            if score >= _SCORE_REPEAT:
                recs.append(self._make_rec(
                    channel_id=channel_id, publication_id=pub_id,
                    rec_type=RecommendationType.repeat_format,
                    priority=RecommendationPriority.medium,
                    title=f"Winning format: replicate "{p['pub_title'][:60]}"",
                    body=(
                        f"This video scored **{score:.0f}/100** — in your top tier. "
                        "Analyse its structure: hook duration, segment count, pacing, thumbnail style. "
                        "Apply the same template to your next 3 videos in this niche."
                    ),
                    rationale=f"Performance score {score:.0f} ≥ 80 repeat threshold.",
                    metric_key="perf_score",
                    metric_current=round(score, 1),
                    metric_target=80.0,
                    impact_label="Stable floor for next videos",
                    expires_at=expires,
                ))

            # ── localize ──────────────────────────────────────────────────────
            if rpm >= _HIGH_RPM and views >= _HIGH_VIEWS_FOR_LOCALIZE:
                recs.append(self._make_rec(
                    channel_id=channel_id, publication_id=pub_id,
                    rec_type=RecommendationType.localize,
                    priority=RecommendationPriority.low,
                    title=f"Localize "{p['pub_title'][:60]}" for high-CPM markets",
                    body=(
                        f"RPM is **${rpm:.2f}** with {int(views):,} views — strong monetisation signal. "
                        "Dub or subtitle into German, French, or Spanish to reach additional high-CPM "
                        "audiences. Even a subtitle track increases discoverability by ~20%."
                    ),
                    rationale=f"RPM ${rpm:.2f} ≥ ${_HIGH_RPM} with {int(views):,} views.",
                    metric_key="rpm",
                    metric_current=round(rpm, 2),
                    metric_target=_HIGH_RPM,
                    impact_label="+20–50% total reach",
                    expires_at=expires,
                ))

        # ── kill_topic / scale_topic ──────────────────────────────────────────
        for tid, tpubs in topic_pubs.items():
            if len(tpubs) < 1:
                continue
            scores = [p["perf_score"] for p in tpubs]
            avg_s  = sum(scores) / len(scores)
            topic_id = uuid.UUID(tid)

            # Fetch topic title
            topic_row = await self.db.execute(
                text("SELECT title FROM topics WHERE id=:id"), {"id": tid}
            )
            t = topic_row.mappings().one_or_none()
            topic_title = t["title"] if t else "this topic"

            if len(tpubs) >= 3 and avg_s < _SCORE_KILL:
                recs.append(self._make_rec(
                    channel_id=channel_id, topic_id=topic_id,
                    rec_type=RecommendationType.kill_topic,
                    priority=RecommendationPriority.medium,
                    title=f"Kill topic: "{topic_title[:60]}"",
                    body=(
                        f"{len(tpubs)} videos on this topic average **{avg_s:.0f}/100** — "
                        "consistently below the 30-point floor. The audience is not interested "
                        "or the competition is too strong. Deprioritise and reallocate "
                        "production capacity to higher-scoring topics."
                    ),
                    rationale=f"Avg perf score {avg_s:.0f} < 30 across {len(tpubs)} publications.",
                    metric_key="avg_perf_score",
                    metric_current=round(avg_s, 1),
                    metric_target=30.0,
                    impact_label="Free up 2+ production slots/month",
                    expires_at=expires,
                ))
            elif len(tpubs) < 3 and avg_s >= _SCORE_REPEAT:
                recs.append(self._make_rec(
                    channel_id=channel_id, topic_id=topic_id,
                    rec_type=RecommendationType.scale_topic,
                    priority=RecommendationPriority.high,
                    title=f"Scale topic: "{topic_title[:60]}"",
                    body=(
                        f"Only {len(tpubs)} video(s) on this topic with avg score "
                        f"**{avg_s:.0f}/100**. You have an underexplored winner. "
                        "Create 3–5 more videos exploring adjacent angles. "
                        "Target long-tail keyword variants while the algorithm favours your channel."
                    ),
                    rationale=f"Avg perf {avg_s:.0f} ≥ 80 with only {len(tpubs)} video(s).",
                    metric_key="avg_perf_score",
                    metric_current=round(avg_s, 1),
                    metric_target=80.0,
                    impact_label="+3–5× topic coverage",
                    expires_at=expires,
                ))

        # Persist all
        for rec in recs:
            self.db.add(rec)
        await self.db.flush()
        log.info(
            "scoring.recommendations_generated",
            channel_id=str(channel_id),
            count=len(recs),
        )
        return recs

    async def list_recommendations(
        self,
        channel_id: uuid.UUID,
        *,
        status: str = "pending",
        limit: int = 50,
    ) -> list[Recommendation]:
        result = await self.db.execute(
            select(Recommendation)
            .where(
                Recommendation.channel_id == channel_id,
                Recommendation.status == status,
            )
            .order_by(
                Recommendation.priority.asc(),
                Recommendation.created_at.desc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def action_recommendation(
        self,
        rec_id: uuid.UUID,
        *,
        action: str,
    ) -> Recommendation:
        rec = await self.db.get(Recommendation, rec_id)
        if rec is None:
            from app.core.exceptions import NotFoundError
            raise NotFoundError("Recommendation not found")

        status_map = {
            "apply":   RecommendationStatus.applied,
            "dismiss": RecommendationStatus.dismissed,
            "snooze":  RecommendationStatus.snoozed,
        }
        rec.status = status_map.get(action, RecommendationStatus.dismissed)
        rec.actioned_at = datetime.now(tz=timezone.utc)
        await self.db.flush()
        return rec

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _make_rec(
        *,
        channel_id: uuid.UUID,
        rec_type: RecommendationType,
        priority: RecommendationPriority,
        title: str,
        body: str,
        rationale: str,
        publication_id: uuid.UUID | None = None,
        topic_id: uuid.UUID | None = None,
        metric_key: str | None = None,
        metric_current: float | None = None,
        metric_target: float | None = None,
        impact_label: str | None = None,
        expires_at: datetime | None = None,
    ) -> Recommendation:
        return Recommendation(
            channel_id=channel_id,
            publication_id=publication_id,
            topic_id=topic_id,
            rec_type=rec_type,
            priority=priority,
            status=RecommendationStatus.pending,
            source=RecommendationSource.rule,
            title=title,
            body=body,
            rationale=rationale,
            metric_key=metric_key,
            metric_current=metric_current,
            metric_target=metric_target,
            impact_label=impact_label,
            expires_at=expires_at,
        )

    async def _aggregate_publication(
        self, pub_id: uuid.UUID, date_from: date, date_to: date
    ) -> dict[str, Any]:
        row = (
            await self.db.execute(
                text("""
                    SELECT
                        COALESCE(SUM(views), 0)                    AS views,
                        COALESCE(AVG(ctr), 0)                      AS ctr,
                        COALESCE(AVG(avg_view_duration_seconds / NULLIF(600,0)), 0) AS retention_pct,
                        COALESCE(AVG(rpm), 0)                      AS rpm,
                        COALESCE(SUM(revenue_usd), 0)              AS revenue
                    FROM analytics_snapshots
                    WHERE publication_id = :pub_id
                      AND snapshot_type = 'publication'
                      AND snapshot_date BETWEEN :from_ AND :to_
                """),
                {"pub_id": str(pub_id), "from_": date_from, "to_": date_to},
            )
        ).mappings().one()
        return dict(row)

    async def _aggregate_channel(
        self, channel_id: uuid.UUID, date_from: date, date_to: date
    ) -> dict[str, Any]:
        row = (
            await self.db.execute(
                text("""
                    SELECT
                        COALESCE(SUM(views), 0)                    AS views,
                        COALESCE(AVG(ctr), 0)                      AS ctr,
                        COALESCE(AVG(avg_view_duration_seconds / NULLIF(600,0)), 0) AS retention_pct,
                        COALESCE(AVG(rpm), 0)                      AS rpm,
                        COALESCE(SUM(revenue_usd), 0)              AS revenue,
                        COALESCE(SUM(subscribers_gained) - SUM(subscribers_lost), 0) AS subs_net
                    FROM analytics_snapshots
                    WHERE channel_id = :cid
                      AND snapshot_type = 'channel'
                      AND snapshot_date BETWEEN :from_ AND :to_
                """),
                {"cid": str(channel_id), "from_": date_from, "to_": date_to},
            )
        ).mappings().one()
        return dict(row)

    async def _channel_median_views(self, channel_id: uuid.UUID, period_days: int) -> float:
        date_to   = date.today()
        date_from = date_to - timedelta(days=period_days - 1)
        row = (
            await self.db.execute(
                text("""
                    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY views) AS median_views
                    FROM analytics_snapshots
                    WHERE channel_id = :cid
                      AND snapshot_type = 'channel'
                      AND snapshot_date BETWEEN :from_ AND :to_
                """),
                {"cid": str(channel_id), "from_": date_from, "to_": date_to},
            )
        ).mappings().one()
        return float(row["median_views"] or 1000)

    async def _upsert_score(
        self,
        *,
        channel_id: uuid.UUID,
        publication_id: uuid.UUID | None,
        period_days: int,
        dims: dict[str, float],
        raw: dict[str, Any],
    ) -> PerformanceScore:
        existing = (
            await self.db.execute(
                select(PerformanceScore).where(
                    PerformanceScore.channel_id == channel_id,
                    PerformanceScore.publication_id == publication_id,
                    PerformanceScore.period_days == period_days,
                )
            )
        ).scalar_one_or_none()

        if existing:
            for k, v in {**dims, **raw}.items():
                setattr(existing, k, v)
            existing.computed_at = datetime.now(tz=timezone.utc)
            await self.db.flush()
            return existing

        score = PerformanceScore(
            channel_id=channel_id,
            publication_id=publication_id,
            period_days=period_days,
            computed_at=datetime.now(tz=timezone.utc),
            **dims,
            **raw,
        )
        self.db.add(score)
        await self.db.flush()
        return score

    async def _rank_publications(self, channel_id: uuid.UUID, period_days: int) -> None:
        await self.db.execute(
            text("""
                WITH ranked AS (
                    SELECT id,
                        RANK() OVER (ORDER BY score DESC) AS rank
                    FROM performance_scores
                    WHERE channel_id = :cid
                      AND publication_id IS NOT NULL
                      AND period_days = :period
                )
                UPDATE performance_scores ps
                SET rank_in_channel = ranked.rank
                FROM ranked WHERE ranked.id = ps.id
            """),
            {"cid": str(channel_id), "period": period_days},
        )

    async def _rank_channels(self, owner_id: uuid.UUID, period_days: int) -> None:
        await self.db.execute(
            text("""
                WITH ranked AS (
                    SELECT ps.id,
                        RANK() OVER (ORDER BY ps.score DESC) AS rank
                    FROM performance_scores ps
                    JOIN channels c ON c.id = ps.channel_id
                    WHERE c.owner_id = :owner_id
                      AND ps.publication_id IS NULL
                      AND ps.period_days = :period
                )
                UPDATE performance_scores ps
                SET rank_overall = ranked.rank
                FROM ranked WHERE ranked.id = ps.id
            """),
            {"owner_id": str(owner_id), "period": period_days},
        )

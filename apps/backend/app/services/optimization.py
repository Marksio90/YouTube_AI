"""
OptimizationService — growth brain orchestrator.

Combines:
  - AnalyticsSnapshot data (CTR/retention/watch-time trends)
  - PerformanceScore data (composite dimensional scores)
  - ContentOptimizerAgent (AI synthesis → next topics, format suggestions, recommendations)

Produces an OptimizationReport stored in the DB and persists high-priority
content_recommendations back into the Recommendation table for the action feed.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.optimization_report import OptimizationReport
from app.db.models.performance import (
    Recommendation,
    RecommendationPriority,
    RecommendationSource,
    RecommendationStatus,
    RecommendationType,
)

log = structlog.get_logger(__name__)

# Priority threshold for pushing AI recs into the Recommendation action feed
_AI_REC_PRIORITIES = {"critical", "high"}
_TREND_PERIOD_DAYS = 7   # "recent" window for trend comparison


class OptimizationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── public api ─────────────────────────────────────────────────────────────

    async def get_latest_report(self, channel_id: uuid.UUID) -> OptimizationReport | None:
        row = (
            await self.db.execute(
                text("""
                    SELECT * FROM optimization_reports
                    WHERE channel_id=:cid
                    ORDER BY updated_at DESC
                    LIMIT 1
                """),
                {"cid": str(channel_id)},
            )
        ).mappings().one_or_none()
        if not row:
            return None
        return await self.db.get(OptimizationReport, row["id"])

    async def generate_report(
        self,
        channel_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        period_days: int = 28,
        task_id: str | None = None,
    ) -> OptimizationReport:
        log_ = log.bind(channel_id=str(channel_id), period_days=period_days)
        log_.info("optimization.generate_report.start")

        # Mark as pending
        report = await self._upsert_report(channel_id, period_days, {"status": "pending", "task_id": task_id})

        try:
            ctx = await self._gather_analytics_context(channel_id, period_days)
            ai_output = await self._run_ai(channel_id, ctx)

            updates: dict[str, Any] = {
                "status": "ready",
                # input metric snapshot
                "channel_score": ctx["channel_score"],
                "ctr_period": ctx["ctr_period"],
                "ctr_trend_pct": ctx["ctr_trend_pct"],
                "retention_period": ctx["retention_period"],
                "retention_trend_pct": ctx["retention_trend_pct"],
                "watch_time_hours": ctx["watch_time_hours"],
                "watch_time_trend_pct": ctx["watch_time_trend_pct"],
                "views_period": ctx["views_period"],
                "views_trend_pct": ctx["views_trend_pct"],
                # AI outputs
                "growth_trajectory": ai_output.growth_trajectory,
                "growth_score": ai_output.growth_score,
                "summary": ai_output.summary,
                "content_recommendations": [r.model_dump() for r in ai_output.content_recommendations],
                "next_topics": [t.model_dump() for t in ai_output.next_topics],
                "format_suggestions": [f.model_dump() for f in ai_output.format_suggestions],
                "watch_time_insights": [w.model_dump() for w in ai_output.watch_time_insights],
                "ctr_insights": [c.model_dump() for c in ai_output.ctr_insights],
                "top_performer_patterns": ai_output.top_performer_patterns,
                "error_message": None,
            }
            report = await self._upsert_report(channel_id, period_days, updates)

            # Persist high-priority AI recs to the recommendation action feed
            await self._persist_ai_recommendations(channel_id, ai_output.content_recommendations)

            # Persist next_topics to the topics table
            await self._persist_next_topics(channel_id, ai_output.next_topics)

            log_.info(
                "optimization.generate_report.complete",
                trajectory=ai_output.growth_trajectory,
                growth_score=ai_output.growth_score,
                recs=len(ai_output.content_recommendations),
                topics=len(ai_output.next_topics),
            )
        except Exception as exc:
            await self._upsert_report(channel_id, period_days, {
                "status": "failed",
                "error_message": str(exc)[:2000],
            })
            raise

        return report

    async def get_publication_insights(
        self,
        publication_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Deep-dive analytics for a single publication."""
        row = (
            await self.db.execute(
                text("""
                    SELECT
                        p.id, p.title, p.duration_seconds,
                        p.view_count, p.like_count, p.comment_count, p.revenue_usd,
                        c.id AS channel_id, c.niche,
                        COALESCE(ps.score, 0)            AS perf_score,
                        COALESCE(ps.ctr_score, 0)        AS ctr_score,
                        COALESCE(ps.retention_score, 0)  AS retention_score,
                        COALESCE(ps.raw_ctr, 0)          AS raw_ctr,
                        COALESCE(ps.raw_retention, 0)    AS raw_retention,
                        COALESCE(ps.raw_views, 0)        AS raw_views,
                        COALESCE(ps.rank_in_channel, NULL) AS rank_in_channel
                    FROM publications p
                    JOIN channels c ON c.id=p.channel_id AND c.owner_id=:owner_id
                    LEFT JOIN performance_scores ps ON ps.publication_id=p.id AND ps.period_days=28
                    WHERE p.id=:pub_id
                """),
                {"pub_id": str(publication_id), "owner_id": str(owner_id)},
            )
        ).mappings().one_or_none()

        if not row:
            from app.core.exceptions import NotFoundError
            raise NotFoundError("Publication not found")

        # 30-day daily trend
        date_to = date.today()
        date_from = date_to - timedelta(days=29)
        snapshots = (
            await self.db.execute(
                text("""
                    SELECT snapshot_date, views, ctr, avg_view_duration_seconds,
                           watch_time_hours, revenue_usd
                    FROM analytics_snapshots
                    WHERE publication_id=:pub_id
                      AND snapshot_type='publication'
                      AND snapshot_date BETWEEN :from_ AND :to_
                    ORDER BY snapshot_date
                """),
                {"pub_id": str(publication_id), "from_": date_from, "to_": date_to},
            )
        ).mappings().all()

        duration = int(row["duration_seconds"] or 600)
        daily = [
            {
                "date": str(s["snapshot_date"]),
                "views": s["views"],
                "ctr": round(float(s["ctr"]) * 100, 2),
                "retention_pct": round(float(s["avg_view_duration_seconds"] or 0) / duration * 100, 1),
                "watch_time_hours": round(float(s["watch_time_hours"]), 2),
            }
            for s in snapshots
        ]

        # Actionable quick-wins
        quick_wins = []
        raw_ctr = float(row["raw_ctr"])
        raw_ret = float(row["raw_retention"])
        if raw_ctr < 0.025:
            quick_wins.append({
                "type": "improve_thumbnail",
                "title": f"CTR {raw_ctr*100:.1f}% — A/B test thumbnail",
                "impact": "Each 1% CTR lift ≈ 25% more clicks at same impressions",
            })
        if raw_ret < 0.30:
            quick_wins.append({
                "type": "improve_hook",
                "title": f"Retention {raw_ret*100:.0f}% — rewrite opening 30s",
                "impact": "Each 10% retention lift ≈ +15% watch time and algorithmic boost",
            })

        return {
            "publication_id": str(publication_id),
            "title": row["title"],
            "perf_score": float(row["perf_score"]),
            "ctr_score": float(row["ctr_score"]),
            "retention_score": float(row["retention_score"]),
            "raw_ctr_pct": round(raw_ctr * 100, 2),
            "raw_retention_pct": round(raw_ret * 100, 1),
            "total_views": int(row["raw_views"]),
            "rank_in_channel": row["rank_in_channel"],
            "daily_trend": daily,
            "quick_wins": quick_wins,
        }

    # ── internal ───────────────────────────────────────────────────────────────

    async def _gather_analytics_context(
        self, channel_id: uuid.UUID, period_days: int
    ) -> dict[str, Any]:
        date_to = date.today()
        date_from = date_to - timedelta(days=period_days - 1)
        prior_from = date_from - timedelta(days=period_days)
        prior_to = date_from - timedelta(days=1)

        # Current period aggregate
        current = (
            await self.db.execute(
                text("""
                    SELECT
                        COALESCE(SUM(views), 0)                           AS views,
                        COALESCE(SUM(watch_time_hours), 0)                AS watch_time_hours,
                        COALESCE(AVG(NULLIF(ctr, 0)), 0)                  AS avg_ctr,
                        COALESCE(AVG(NULLIF(avg_view_duration_seconds,0)),0) AS avg_duration_sec,
                        COALESCE(SUM(revenue_usd), 0)                     AS revenue,
                        COALESCE(AVG(NULLIF(rpm, 0)), 0)                  AS avg_rpm,
                        COALESCE(SUM(subscribers_gained)-SUM(subscribers_lost),0) AS net_subs
                    FROM analytics_snapshots
                    WHERE channel_id=:cid
                      AND snapshot_type='channel'
                      AND snapshot_date BETWEEN :from_ AND :to_
                """),
                {"cid": str(channel_id), "from_": date_from, "to_": date_to},
            )
        ).mappings().one()

        # Prior period aggregate (for trends)
        prior = (
            await self.db.execute(
                text("""
                    SELECT
                        COALESCE(SUM(views), 0)                         AS views,
                        COALESCE(SUM(watch_time_hours), 0)              AS watch_time_hours,
                        COALESCE(AVG(NULLIF(ctr, 0)), 0)                AS avg_ctr,
                        COALESCE(AVG(NULLIF(avg_view_duration_seconds,0)),0) AS avg_duration_sec
                    FROM analytics_snapshots
                    WHERE channel_id=:cid
                      AND snapshot_type='channel'
                      AND snapshot_date BETWEEN :from_ AND :to_
                """),
                {"cid": str(channel_id), "from_": prior_from, "to_": prior_to},
            )
        ).mappings().one()

        def _trend(curr: float, prev: float) -> float:
            if prev <= 0:
                return 0.0
            return round((curr - prev) / prev * 100, 1)

        # Channel performance score
        score_row = (
            await self.db.execute(
                text("""
                    SELECT COALESCE(score, 0) AS score
                    FROM performance_scores
                    WHERE channel_id=:cid AND publication_id IS NULL AND period_days=:period
                    ORDER BY computed_at DESC LIMIT 1
                """),
                {"cid": str(channel_id), "period": period_days},
            )
        ).mappings().one_or_none()
        channel_score = float(score_row["score"]) if score_row else 0.0

        # Top 5 publications by perf_score
        top_pubs = (
            await self.db.execute(
                text("""
                    SELECT
                        p.title, p.duration_seconds,
                        COALESCE(SUM(s.views), 0)                                AS views,
                        COALESCE(AVG(NULLIF(s.ctr, 0)), 0)                       AS ctr,
                        COALESCE(AVG(NULLIF(s.avg_view_duration_seconds, 0) /
                            NULLIF(p.duration_seconds, 600)), 0)                 AS retention_pct,
                        COALESCE(SUM(s.watch_time_hours), 0)                     AS watch_time_hours,
                        COALESCE(SUM(s.revenue_usd), 0)                          AS revenue,
                        COALESCE(ps.score, 0)                                    AS perf_score
                    FROM publications p
                    LEFT JOIN analytics_snapshots s ON s.publication_id=p.id
                        AND s.snapshot_type='publication'
                        AND s.snapshot_date BETWEEN :from_ AND :to_
                    LEFT JOIN performance_scores ps ON ps.publication_id=p.id
                        AND ps.period_days=:period
                    WHERE p.channel_id=:cid AND p.status='published'
                    GROUP BY p.id, p.title, p.duration_seconds, ps.score
                    ORDER BY ps.score DESC NULLS LAST
                    LIMIT 5
                """),
                {"cid": str(channel_id), "from_": date_from, "to_": date_to, "period": period_days},
            )
        ).mappings().all()

        # Bottom 5
        bottom_pubs = (
            await self.db.execute(
                text("""
                    SELECT
                        p.title, p.duration_seconds,
                        COALESCE(SUM(s.views), 0)                                AS views,
                        COALESCE(AVG(NULLIF(s.ctr, 0)), 0)                       AS ctr,
                        COALESCE(AVG(NULLIF(s.avg_view_duration_seconds, 0) /
                            NULLIF(p.duration_seconds, 600)), 0)                 AS retention_pct,
                        COALESCE(SUM(s.watch_time_hours), 0)                     AS watch_time_hours,
                        COALESCE(SUM(s.revenue_usd), 0)                          AS revenue,
                        COALESCE(ps.score, 0)                                    AS perf_score
                    FROM publications p
                    LEFT JOIN analytics_snapshots s ON s.publication_id=p.id
                        AND s.snapshot_type='publication'
                        AND s.snapshot_date BETWEEN :from_ AND :to_
                    LEFT JOIN performance_scores ps ON ps.publication_id=p.id
                        AND ps.period_days=:period
                    WHERE p.channel_id=:cid AND p.status='published'
                    GROUP BY p.id, p.title, p.duration_seconds, ps.score
                    ORDER BY ps.score ASC NULLS LAST
                    LIMIT 5
                """),
                {"cid": str(channel_id), "from_": date_from, "to_": date_to, "period": period_days},
            )
        ).mappings().all()

        # Format performance (bucket by duration)
        format_perf = (
            await self.db.execute(
                text("""
                    SELECT
                        CASE
                            WHEN COALESCE(p.duration_seconds, 0) < 300   THEN 'short'
                            WHEN COALESCE(p.duration_seconds, 0) < 900   THEN 'medium'
                            ELSE 'long'
                        END                                                  AS duration_bucket,
                        COUNT(DISTINCT p.id)                                 AS video_count,
                        COALESCE(AVG(NULLIF(s.views, 0)), 0)                AS avg_views,
                        COALESCE(AVG(NULLIF(s.ctr, 0)), 0)                  AS avg_ctr,
                        COALESCE(AVG(NULLIF(s.avg_view_duration_seconds,0) /
                            NULLIF(p.duration_seconds, 600)), 0)             AS avg_retention_pct,
                        COALESCE(AVG(NULLIF(s.watch_time_hours, 0)), 0)     AS avg_watch_time_hours
                    FROM publications p
                    LEFT JOIN analytics_snapshots s ON s.publication_id=p.id
                        AND s.snapshot_type='publication'
                        AND s.snapshot_date BETWEEN :from_ AND :to_
                    WHERE p.channel_id=:cid AND p.status='published'
                    GROUP BY duration_bucket
                    ORDER BY avg_views DESC
                """),
                {"cid": str(channel_id), "from_": date_from, "to_": date_to},
            )
        ).mappings().all()

        # Existing topic pipeline
        existing_topics = (
            await self.db.execute(
                text("""
                    SELECT title FROM topics
                    WHERE channel_id=:cid AND status NOT IN ('rejected','archived')
                    ORDER BY created_at DESC LIMIT 30
                """),
                {"cid": str(channel_id)},
            )
        ).scalars().all()

        # Channel info
        channel = (
            await self.db.execute(
                text("SELECT name, niche FROM channels WHERE id=:cid"),
                {"cid": str(channel_id)},
            )
        ).mappings().one()

        cur_duration = float(current["avg_duration_sec"] or 0)
        pub_duration_estimate = cur_duration if cur_duration > 0 else 600.0
        retention_period = float(current["avg_duration_sec"] or 0) / pub_duration_estimate if pub_duration_estimate > 0 else 0.0
        prior_retention = float(prior["avg_duration_sec"] or 0) / pub_duration_estimate if pub_duration_estimate > 0 else 0.0

        def _to_pub_row(r: Any) -> dict:
            return {
                "title": str(r["title"])[:80],
                "views": int(r["views"]),
                "ctr": float(r["ctr"]),
                "retention_pct": float(r["retention_pct"]),
                "watch_time_hours": float(r["watch_time_hours"]),
                "revenue_usd": float(r["revenue"]),
                "perf_score": float(r["perf_score"]),
                "duration_seconds": int(r["duration_seconds"] or 0),
            }

        def _to_fmt_row(r: Any) -> dict:
            return {
                "duration_bucket": r["duration_bucket"],
                "video_count": int(r["video_count"]),
                "avg_views": float(r["avg_views"]),
                "avg_ctr": float(r["avg_ctr"]),
                "avg_retention_pct": float(r["avg_retention_pct"]),
                "avg_watch_time_hours": float(r["avg_watch_time_hours"]),
            }

        return {
            "channel_name": channel["name"],
            "niche": channel["niche"] or "general",
            "channel_score": channel_score,
            # current period
            "views_period": int(current["views"]),
            "watch_time_hours": float(current["watch_time_hours"]),
            "ctr_period": float(current["avg_ctr"]),
            "retention_period": retention_period,
            "revenue_usd": float(current["revenue"]),
            "avg_rpm": float(current["avg_rpm"]),
            "net_subs": int(current["net_subs"]),
            # trends
            "views_trend_pct": _trend(float(current["views"]), float(prior["views"])),
            "watch_time_trend_pct": _trend(float(current["watch_time_hours"]), float(prior["watch_time_hours"])),
            "ctr_trend_pct": _trend(float(current["avg_ctr"]), float(prior["avg_ctr"])),
            "retention_trend_pct": _trend(retention_period, prior_retention),
            # structured data
            "top_publications": [_to_pub_row(r) for r in top_pubs],
            "bottom_publications": [_to_pub_row(r) for r in bottom_pubs],
            "format_performance": [_to_fmt_row(r) for r in format_perf],
            "existing_topic_titles": list(existing_topics),
        }

    async def _run_ai(self, channel_id: uuid.UUID, ctx: dict):
        from worker.agents.content_optimizer import (
            ChannelMetrics,
            ContentOptimizerAgent,
            FormatPerformanceRow,
            OptimizationInput,
            PublicationMetricRow,
        )
        from worker.config import settings as worker_settings

        inp = OptimizationInput(
            channel_name=ctx["channel_name"],
            niche=ctx["niche"],
            period_days=28,
            metrics=ChannelMetrics(
                total_views=ctx["views_period"],
                avg_ctr=ctx["ctr_period"],
                avg_retention_pct=ctx["retention_period"],
                total_watch_time_hours=ctx["watch_time_hours"],
                avg_rpm=ctx["avg_rpm"],
                total_revenue_usd=ctx["revenue_usd"],
                net_subscribers=ctx["net_subs"],
            ),
            ctr_trend_pct=ctx["ctr_trend_pct"],
            watch_time_trend_pct=ctx["watch_time_trend_pct"],
            views_trend_pct=ctx["views_trend_pct"],
            retention_trend_pct=ctx["retention_trend_pct"],
            top_publications=[PublicationMetricRow(**p) for p in ctx["top_publications"]],
            bottom_publications=[PublicationMetricRow(**p) for p in ctx["bottom_publications"]],
            format_performance=[FormatPerformanceRow(**f) for f in ctx["format_performance"]],
            existing_topic_titles=ctx["existing_topic_titles"],
        )

        agent = ContentOptimizerAgent()
        return await agent.run(inp)

    async def _upsert_report(
        self, channel_id: uuid.UUID, period_days: int, updates: dict[str, Any]
    ) -> OptimizationReport:
        existing = (
            await self.db.execute(
                text("""
                    SELECT id FROM optimization_reports
                    WHERE channel_id=:cid AND period_days=:period
                """),
                {"cid": str(channel_id), "period": period_days},
            )
        ).mappings().one_or_none()

        if existing:
            report = await self.db.get(OptimizationReport, existing["id"])
            for k, v in updates.items():
                setattr(report, k, v)
            report.updated_at = datetime.now(tz=timezone.utc)
            await self.db.flush()
            return report

        report = OptimizationReport(
            channel_id=channel_id,
            period_days=period_days,
            **updates,
        )
        self.db.add(report)
        await self.db.flush()
        return report

    async def _persist_ai_recommendations(
        self, channel_id: uuid.UUID, content_recs: list
    ) -> None:
        if not content_recs:
            return

        # Clear stale AI pending recs for this channel
        await self.db.execute(
            text("""
                DELETE FROM recommendations
                WHERE channel_id=:cid AND source='ai' AND status='pending'
            """),
            {"cid": str(channel_id)},
        )

        from datetime import timedelta
        expires = datetime.now(tz=timezone.utc) + timedelta(days=14)

        for rec in content_recs:
            priority = rec.priority if hasattr(rec, "priority") else rec.get("priority", "medium")
            if priority not in _AI_REC_PRIORITIES:
                continue

            rec_type_val = rec.rec_type if hasattr(rec, "rec_type") else rec.get("rec_type", "improve_hook")
            try:
                rec_type = RecommendationType(rec_type_val)
            except ValueError:
                rec_type = RecommendationType.improve_hook

            new_rec = Recommendation(
                channel_id=channel_id,
                rec_type=rec_type,
                priority=RecommendationPriority(priority),
                status=RecommendationStatus.pending,
                source=RecommendationSource.ai,
                title=rec.title if hasattr(rec, "title") else rec.get("title", ""),
                body=rec.body if hasattr(rec, "body") else rec.get("body", ""),
                rationale=rec.evidence if hasattr(rec, "evidence") else rec.get("evidence", ""),
                metric_key=rec.metric_key if hasattr(rec, "metric_key") else rec.get("metric_key"),
                metric_current=rec.metric_current if hasattr(rec, "metric_current") else rec.get("metric_current"),
                metric_target=rec.metric_target if hasattr(rec, "metric_target") else rec.get("metric_target"),
                impact_label=rec.impact_label if hasattr(rec, "impact_label") else rec.get("impact_label"),
                expires_at=expires,
            )
            self.db.add(new_rec)

        await self.db.flush()

    async def _persist_next_topics(self, channel_id: uuid.UUID, next_topics: list) -> None:
        for topic in next_topics[:10]:
            title = topic.title if hasattr(topic, "title") else topic.get("title", "")
            rationale = topic.rationale if hasattr(topic, "rationale") else topic.get("rationale", "")
            est_views = topic.estimated_views if hasattr(topic, "estimated_views") else topic.get("estimated_views", 0)
            trend_score = min(10.0, est_views / 10_000)

            await self.db.execute(
                text("""
                    INSERT INTO topics
                        (id, channel_id, title, description, keywords, source, status, trend_score)
                    VALUES
                        (gen_random_uuid(), :cid, :title, :desc, '{}', 'ai_optimized', 'new', :score)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "cid": str(channel_id),
                    "title": str(title)[:300],
                    "desc": str(rationale)[:2000],
                    "score": trend_score,
                },
            )
        await self.db.flush()

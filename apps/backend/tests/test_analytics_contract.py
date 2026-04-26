from datetime import date
from uuid import uuid4

from pydantic import ValidationError
import pytest

from app.schemas.analytics import AnalyticsAggregate, AnalyticsSnapshotCreate, DimensionalScores


def test_analytics_snapshot_contract_accepts_valid_payload() -> None:
    payload = AnalyticsSnapshotCreate(
        channel_id=uuid4(),
        snapshot_date=date(2026, 1, 10),
        views=1_250,
        ctr=6.4,
        watch_time_hours=220.5,
    )

    assert payload.snapshot_type == "channel"
    assert payload.views == 1_250


def test_dimensional_scores_contract_enforces_range() -> None:
    with pytest.raises(ValidationError):
        DimensionalScores(
            view_score=101,
            ctr_score=50,
            retention_score=50,
            revenue_score=50,
            growth_score=50,
        )


def test_analytics_aggregate_contract_defaults_daily_snapshots() -> None:
    aggregate = AnalyticsAggregate(
        channel_id=uuid4(),
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 7),
        total_views=20_000,
        total_watch_time_hours=120.0,
        total_revenue_usd=80.0,
        subscribers_gained=120,
        subscribers_lost=20,
        net_subscribers=100,
        avg_rpm=4.0,
        avg_ctr=5.2,
    )

    assert aggregate.daily_snapshots == []

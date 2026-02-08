"""Tests for observability module.

Covers:
1. test_percentile_computation
2. test_ttfr_session_matching
3. test_daily_metrics_upsert_uniqueness
4. test_alert_triggers
5. test_bot_metrics_hit_rate
6. test_channel_metrics_avg_score
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. test_percentile_computation
# ---------------------------------------------------------------------------


class TestPercentileComputation:
    """Verify the percentile function for various inputs."""

    def test_median_of_odd_list(self):
        from app.observability.slo import percentile

        assert percentile([1, 2, 3, 4, 5], 50) == 3

    def test_median_of_even_list(self):
        from app.observability.slo import percentile

        result = percentile([1, 2, 3, 4], 50)
        assert result in (2, 3)  # nearest-rank

    def test_p90(self):
        from app.observability.slo import percentile

        values = list(range(1, 101))  # 1..100
        result = percentile(values, 90)
        assert result == 90

    def test_p0(self):
        from app.observability.slo import percentile

        assert percentile([10, 20, 30], 0) == 10

    def test_p100(self):
        from app.observability.slo import percentile

        assert percentile([10, 20, 30], 100) == 30

    def test_empty_list(self):
        from app.observability.slo import percentile

        assert percentile([], 50) == 0.0

    def test_single_element(self):
        from app.observability.slo import percentile

        assert percentile([42.0], 90) == 42.0

    def test_unsorted_input(self):
        from app.observability.slo import percentile

        result = percentile([5, 1, 3, 2, 4], 50)
        assert result == 3


# ---------------------------------------------------------------------------
# 2. test_ttfr_session_matching
# ---------------------------------------------------------------------------


class TestTTFRSessionMatching:
    """TTFR should pair bot_start with next recommendation_shown within 30 min."""

    @pytest.mark.asyncio
    async def test_matches_within_window(self):
        from app.observability.slo import compute_ttfr

        now = datetime(2026, 2, 5, 12, 0, 0, tzinfo=timezone.utc)

        # Create mock events
        start_event = MagicMock()
        start_event.user_id = "u1"
        start_event.created_at = now

        rec_event = MagicMock()
        rec_event.user_id = "u1"
        rec_event.created_at = now + timedelta(seconds=5)

        mock_events_repo = AsyncMock()

        def mock_list_events(event_name=None, since_dt=None, limit=200):
            if event_name == "bot_start":
                return [start_event]
            elif event_name == "recommendation_shown":
                return [rec_event]
            return []

        mock_events_repo.list_events = AsyncMock(side_effect=mock_list_events)

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        patches = {
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
            "er_mod": patch("app.storage.repo_events.EventsRepo"),
            "er_pkg": patch("app.storage.EventsRepo"),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory
            for k in ("er_mod", "er_pkg"):
                mocks[k].return_value = mock_events_repo

            result = await compute_ttfr("2026-02-05")

            assert result["sample_count"] == 1
            assert result["p50"] == 5.0
            assert result["p90"] == 5.0
        finally:
            for p in patches.values():
                p.stop()

    @pytest.mark.asyncio
    async def test_no_match_outside_window(self):
        from app.observability.slo import compute_ttfr

        now = datetime(2026, 2, 5, 12, 0, 0, tzinfo=timezone.utc)

        start_event = MagicMock()
        start_event.user_id = "u1"
        start_event.created_at = now

        # Rec is 45 min later — outside 30 min window
        rec_event = MagicMock()
        rec_event.user_id = "u1"
        rec_event.created_at = now + timedelta(minutes=45)

        mock_events_repo = AsyncMock()

        def mock_list_events(event_name=None, since_dt=None, limit=200):
            if event_name == "bot_start":
                return [start_event]
            elif event_name == "recommendation_shown":
                return [rec_event]
            return []

        mock_events_repo.list_events = AsyncMock(side_effect=mock_list_events)

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        patches = {
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
            "er_mod": patch("app.storage.repo_events.EventsRepo"),
            "er_pkg": patch("app.storage.EventsRepo"),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory
            for k in ("er_mod", "er_pkg"):
                mocks[k].return_value = mock_events_repo

            result = await compute_ttfr("2026-02-05")
            assert result["sample_count"] == 0
        finally:
            for p in patches.values():
                p.stop()


# ---------------------------------------------------------------------------
# 3. test_daily_metrics_upsert_uniqueness
# ---------------------------------------------------------------------------


class TestDailyMetricsUpsert:
    """Upsert should update existing metric instead of creating duplicate."""

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self):
        from app.storage.repo_daily_metrics import DailyMetricsRepo
        from app.storage.models import DailyMetric

        mock_session = AsyncMock()

        # First call: existing metric found
        existing_metric = MagicMock(spec=DailyMetric)
        existing_metric.value = 10.0
        existing_metric.updated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_metric
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        repo = DailyMetricsRepo(mock_session)
        result = await repo.upsert_metric("2026-02-05", "bot_dau", 42.0)

        assert result.value == 42.0
        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_upsert_creates_new(self):
        from app.storage.repo_daily_metrics import DailyMetricsRepo

        mock_session = AsyncMock()

        # No existing metric
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.add = MagicMock()

        repo = DailyMetricsRepo(mock_session)
        result = await repo.upsert_metric("2026-02-05", "bot_dau", 42.0)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called()


# ---------------------------------------------------------------------------
# 4. test_alert_triggers
# ---------------------------------------------------------------------------


class TestAlertTriggers:
    """Alert checks should create alerts when thresholds are breached."""

    @pytest.mark.asyncio
    async def test_ttfr_high_alert(self):
        from app.observability.runner import run_alert_checks
        from app.storage.models import DailyMetric

        # Mock a TTFR p90 metric that exceeds threshold (30s)
        ttfr_metric = MagicMock(spec=DailyMetric)
        ttfr_metric.value = 45.0
        ttfr_metric.date = "2026-02-05"

        mock_metrics_repo = AsyncMock()
        mock_metrics_repo.get_latest = AsyncMock(
            side_effect=lambda name: ttfr_metric if name == "slo_ttfr_p90" else None
        )

        mock_alerts_repo = AsyncMock()
        mock_alerts_repo.has_recent_alert = AsyncMock(return_value=False)
        mock_alerts_repo.add_alert = AsyncMock()

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        patches = {
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
            "dm_mod": patch("app.storage.repo_daily_metrics.DailyMetricsRepo"),
            "dm_pkg": patch("app.storage.DailyMetricsRepo"),
            "al_mod": patch("app.storage.repo_alerts.AlertsRepo"),
            "al_pkg": patch("app.storage.AlertsRepo"),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory
            for k in ("dm_mod", "dm_pkg"):
                mocks[k].return_value = mock_metrics_repo
            for k in ("al_mod", "al_pkg"):
                mocks[k].return_value = mock_alerts_repo

            result = await run_alert_checks()

            assert result["alerts_created"] >= 1
            mock_alerts_repo.add_alert.assert_called()
            # Verify the TTFR alert was created
            call_args = mock_alerts_repo.add_alert.call_args_list
            ttfr_calls = [
                c for c in call_args
                if c.kwargs.get("alert_type") == "TTFR_P90_HIGH"
            ]
            assert len(ttfr_calls) == 1
        finally:
            for p in patches.values():
                p.stop()

    @pytest.mark.asyncio
    async def test_no_alert_when_below_threshold(self):
        from app.observability.runner import run_alert_checks
        from app.storage.models import DailyMetric

        # TTFR p90 below threshold
        ttfr_metric = MagicMock(spec=DailyMetric)
        ttfr_metric.value = 5.0
        ttfr_metric.date = "2026-02-05"

        mock_metrics_repo = AsyncMock()
        mock_metrics_repo.get_latest = AsyncMock(
            side_effect=lambda name: ttfr_metric if name == "slo_ttfr_p90" else None
        )

        mock_alerts_repo = AsyncMock()
        mock_alerts_repo.has_recent_alert = AsyncMock(return_value=False)
        mock_alerts_repo.add_alert = AsyncMock()

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        patches = {
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
            "dm_mod": patch("app.storage.repo_daily_metrics.DailyMetricsRepo"),
            "dm_pkg": patch("app.storage.DailyMetricsRepo"),
            "al_mod": patch("app.storage.repo_alerts.AlertsRepo"),
            "al_pkg": patch("app.storage.AlertsRepo"),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory
            for k in ("dm_mod", "dm_pkg"):
                mocks[k].return_value = mock_metrics_repo
            for k in ("al_mod", "al_pkg"):
                mocks[k].return_value = mock_alerts_repo

            result = await run_alert_checks()
            assert result["alerts_created"] == 0
        finally:
            for p in patches.values():
                p.stop()

    @pytest.mark.asyncio
    async def test_dedup_prevents_duplicate_alert(self):
        from app.observability.runner import run_alert_checks
        from app.storage.models import DailyMetric

        ttfr_metric = MagicMock(spec=DailyMetric)
        ttfr_metric.value = 45.0
        ttfr_metric.date = "2026-02-05"

        mock_metrics_repo = AsyncMock()
        mock_metrics_repo.get_latest = AsyncMock(
            side_effect=lambda name: ttfr_metric if name == "slo_ttfr_p90" else None
        )

        mock_alerts_repo = AsyncMock()
        # Already has a recent alert
        mock_alerts_repo.has_recent_alert = AsyncMock(return_value=True)
        mock_alerts_repo.add_alert = AsyncMock()

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        patches = {
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
            "dm_mod": patch("app.storage.repo_daily_metrics.DailyMetricsRepo"),
            "dm_pkg": patch("app.storage.DailyMetricsRepo"),
            "al_mod": patch("app.storage.repo_alerts.AlertsRepo"),
            "al_pkg": patch("app.storage.AlertsRepo"),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory
            for k in ("dm_mod", "dm_pkg"):
                mocks[k].return_value = mock_metrics_repo
            for k in ("al_mod", "al_pkg"):
                mocks[k].return_value = mock_alerts_repo

            result = await run_alert_checks()
            assert result["alerts_created"] == 0
            mock_alerts_repo.add_alert.assert_not_called()
        finally:
            for p in patches.values():
                p.stop()


# ---------------------------------------------------------------------------
# 5. test_bot_metrics_hit_rate
# ---------------------------------------------------------------------------


class TestBotMetricsHitRate:
    """Bot metrics should correctly compute hit rate from feedback."""

    @pytest.mark.asyncio
    async def test_hit_rate_calculation(self):
        from app.observability.bot_metrics import compute_bot_metrics

        mock_session = AsyncMock()

        # Set up return values for each query
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()

            if call_count == 1:
                # sessions count
                result.scalar.return_value = 100
            elif call_count == 2:
                # DAU count
                result.scalar.return_value = 50
            elif call_count == 3:
                # hit count
                result.scalar.return_value = 30
            elif call_count == 4:
                # miss count
                result.scalar.return_value = 10
            elif call_count == 5:
                # another count
                result.scalar.return_value = 10
            elif call_count == 6:
                # favorite count
                result.scalar.return_value = 5
            elif call_count == 7:
                # share count
                result.scalar.return_value = 3
            else:
                result.scalar.return_value = 0

            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        patches = {
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory

            result = await compute_bot_metrics("2026-02-05")

            assert result["bot_sessions"] == 100.0
            assert result["bot_dau"] == 50.0
            # hit_rate = 30 / (30+10+10) = 0.6
            assert result["bot_hit_rate"] == 0.6
            # miss_rate = 10 / 50 = 0.2
            assert result["bot_miss_rate"] == 0.2
        finally:
            for p in patches.values():
                p.stop()


# ---------------------------------------------------------------------------
# 6. test_channel_metrics_avg_score
# ---------------------------------------------------------------------------


class TestChannelMetricsAvgScore:
    """Channel metrics should compute correct avg post score."""

    @pytest.mark.asyncio
    async def test_avg_score(self):
        from app.observability.channel_metrics import compute_channel_metrics

        mock_session = AsyncMock()

        # Create mock posts
        post1 = MagicMock()
        post1.post_id = "p1"
        post1.format_id = "poll"
        post1.published_at = datetime(2026, 2, 5, 10, 0, 0, tzinfo=timezone.utc)

        post2 = MagicMock()
        post2.post_id = "p2"
        post2.format_id = "one_pick_emotion"
        post2.published_at = datetime(2026, 2, 5, 19, 0, 0, tzinfo=timezone.utc)

        snap1 = MagicMock()
        snap1.score = 40.0
        snap1.bot_clicks = 5

        snap2 = MagicMock()
        snap2.score = 60.0
        snap2.bot_clicks = 10

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()

            if call_count == 1:
                # Posts query
                result.scalars.return_value.all.return_value = [post1, post2]
            elif call_count == 2:
                # Snap for p1
                result.scalar_one_or_none.return_value = snap1
            elif call_count == 3:
                # Snap for p2
                result.scalar_one_or_none.return_value = snap2
            else:
                result.scalar_one_or_none.return_value = None

            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        patches = {
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory

            result = await compute_channel_metrics("2026-02-05")

            assert result["channel_posts_published"] == 2.0
            assert result["channel_avg_post_score"] == 50.0  # (40+60)/2
            assert result["channel_total_bot_clicks"] == 15.0
            assert result["channel_clicks_poll"] == 5.0
            assert result["channel_clicks_one_pick_emotion"] == 10.0
        finally:
            for p in patches.values():
                p.stop()


# ---------------------------------------------------------------------------
# 7. test_admin_endpoints_auth
# ---------------------------------------------------------------------------


class TestObservabilityEndpointsAuth:
    """Observability admin endpoints should require authentication."""

    @pytest.mark.asyncio
    async def test_daily_metrics_requires_auth(self):
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/metrics/daily")
            assert resp.status_code in (401, 503)

    @pytest.mark.asyncio
    async def test_alerts_requires_auth(self):
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/alerts")
            assert resp.status_code in (401, 503)

    @pytest.mark.asyncio
    async def test_ttfr_requires_auth(self):
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/slo/ttfr")
            assert resp.status_code in (401, 503)

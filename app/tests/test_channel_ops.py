"""Tests for autonomous channel operations.

Covers:
1. test_deeplink_in_meta_json
2. test_post_score_formula
3. test_ab_winner_picks_highest
4. test_bot_clicks_aggregator_counts_events
5. test_metrics_ingest_requires_admin_token
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. test_deeplink_in_meta_json
# ---------------------------------------------------------------------------


class TestDeeplinkInMetaJson:
    """Deep-link URL, hypothesis_id and variant_id must appear in meta_json."""

    @pytest.mark.asyncio
    async def test_deeplink_in_meta_json(self):
        """run_publish_post writes deeplink + ids into meta_json."""
        from app.jobs.publish_posts import run_publish_post

        mock_msg = MagicMock()
        mock_msg.message_id = 99

        mock_generated = MagicMock()
        mock_generated.text = "Пост з діплінком"
        mock_generated.meta_json = json.dumps({"items": ["i1"], "format_id": "poll"})
        mock_generated.used_llm = False
        mock_generated.lint_passed = True
        mock_generated.poster_url = None

        mock_posts_repo = AsyncMock()
        mock_events_repo = AsyncMock()
        mock_ab_repo = AsyncMock()
        mock_ab_repo.get_active_winner = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        patches = {
            "config": patch("app.jobs.publish_posts.config"),
            "send": patch("app.bot.sender.safe_send_message", new_callable=AsyncMock),
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
            "pr_mod": patch("app.storage.repo_posts.PostsRepo"),
            "pr_pkg": patch("app.storage.PostsRepo"),
            "er_mod": patch("app.storage.repo_events.EventsRepo"),
            "er_pkg": patch("app.storage.EventsRepo"),
            "ab_mod": patch("app.storage.repo_ab_winners.ABWinnersRepo"),
            "ab_pkg": patch("app.storage.ABWinnersRepo"),
            "gen": patch("app.content.generator.generate_post", new_callable=AsyncMock),
            "bot": patch("app.main.bot"),
            "bandit": patch(
                "app.jobs.publish_posts._pick_format_bandit",
                new_callable=AsyncMock,
                return_value="poll",
            ),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            mocks["config"].channel_post_enabled = True
            mocks["config"].channel_id = "-100123"
            mocks["config"].bot_username = "testbot"

            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory
            mocks["send"].return_value = mock_msg
            mocks["gen"].return_value = mock_generated

            for k in ("pr_mod", "pr_pkg"):
                mocks[k].return_value = mock_posts_repo
            mock_posts_repo.list_recent_posts = AsyncMock(return_value=[])
            mock_posts_repo.create_post = AsyncMock()

            for k in ("er_mod", "er_pkg"):
                mocks[k].return_value = mock_events_repo
            mock_events_repo.log_event = AsyncMock()

            for k in ("ab_mod", "ab_pkg"):
                mocks[k].return_value = mock_ab_repo

            result = await run_publish_post(slot_index=0)

            assert result.ok is True

            # Inspect the meta_json that was saved
            call_kwargs = mock_posts_repo.create_post.call_args.kwargs
            saved_meta = json.loads(call_kwargs["meta_json"])

            assert "deeplink" in saved_meta
            assert "?start=post_" in saved_meta["deeplink"]
            assert "hypothesis_id" in saved_meta
            assert "variant_id" in saved_meta
            assert saved_meta["variant_id"] in ("v-a", "v-b")
            assert "telegram_message_id" in saved_meta
            assert saved_meta["telegram_message_id"] == "99"
        finally:
            for p in patches.values():
                p.stop()


# ---------------------------------------------------------------------------
# 2. test_post_score_formula
# ---------------------------------------------------------------------------


class TestPostScoreFormula:
    """Verify the scoring formula: reactions*2 + forwards*3 + bot_clicks*4 - unsub_delta*5."""

    def test_basic_formula(self):
        from app.jobs.compute_scores import calculate_score

        score = calculate_score(reactions=10, forwards=5, bot_clicks=3, unsub_delta=2)
        #  10*2 + 5*3 + 3*4 - 2*5 = 20 + 15 + 12 - 10 = 37
        assert score == 37.0

    def test_zero_inputs(self):
        from app.jobs.compute_scores import calculate_score

        assert calculate_score(0, 0, 0, 0) == 0.0

    def test_negative_from_unsubs(self):
        from app.jobs.compute_scores import calculate_score

        score = calculate_score(reactions=0, forwards=0, bot_clicks=0, unsub_delta=5)
        assert score == -25.0

    def test_only_clicks(self):
        from app.jobs.compute_scores import calculate_score

        score = calculate_score(reactions=0, forwards=0, bot_clicks=10, unsub_delta=0)
        assert score == 40.0


# ---------------------------------------------------------------------------
# 3. test_ab_winner_picks_highest
# ---------------------------------------------------------------------------


class TestABWinnerPicksHighest:
    """The A/B winner job must pick the variant with the highest avg score."""

    @pytest.mark.asyncio
    async def test_picks_highest_avg(self):
        from app.jobs.ab_winner import run_ab_winner_selection

        now = datetime.now(timezone.utc)

        # Build mock rows: (hypothesis_id, variant_id, score)
        mock_rows = [
            ("h-test", "v-a", 10.0),
            ("h-test", "v-a", 20.0),
            ("h-test", "v-b", 50.0),
            ("h-test", "v-b", 60.0),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        mock_ab_repo = AsyncMock()
        mock_ab_repo.get_active_winner = AsyncMock(return_value=None)
        mock_ab_repo.set_winner = AsyncMock()

        mock_events_repo = AsyncMock()
        mock_events_repo.log_event = AsyncMock()

        patches = {
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
            "ab_mod": patch("app.storage.repo_ab_winners.ABWinnersRepo"),
            "ab_pkg": patch("app.storage.ABWinnersRepo"),
            "er_mod": patch("app.storage.repo_events.EventsRepo"),
            "er_pkg": patch("app.storage.EventsRepo"),
            "config": patch("app.jobs.ab_winner.config"),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory
            for k in ("ab_mod", "ab_pkg"):
                mocks[k].return_value = mock_ab_repo
            for k in ("er_mod", "er_pkg"):
                mocks[k].return_value = mock_events_repo

            mocks["config"].ab_default_duration_days = 7

            result = await run_ab_winner_selection()

            assert result["winners_set"] == 1
            mock_ab_repo.set_winner.assert_called_once()
            winner_call = mock_ab_repo.set_winner.call_args
            assert winner_call.kwargs["winner_variant_id"] == "v-b"
            assert winner_call.kwargs["hypothesis_id"] == "h-test"
        finally:
            for p in patches.values():
                p.stop()


# ---------------------------------------------------------------------------
# 4. test_bot_clicks_aggregator_counts_events
# ---------------------------------------------------------------------------


class TestBotClicksAggregator:
    """The aggregator must count events and upsert post_metrics.bot_clicks."""

    @pytest.mark.asyncio
    async def test_counts_events(self):
        from app.jobs.bot_clicks_aggregator import run_bot_clicks_aggregator

        now = datetime.now(timezone.utc)

        # Build mock events
        def _make_event(post_id: str):
            ev = MagicMock()
            ev.payload_json = json.dumps({"post_id": post_id, "variant_id": "v-a"})
            return ev

        mock_events = [
            _make_event("p1"),
            _make_event("p1"),
            _make_event("p1"),
            _make_event("p2"),
        ]

        mock_events_repo = AsyncMock()
        mock_events_repo.list_events = AsyncMock(return_value=mock_events)

        mock_metrics_repo = AsyncMock()
        mock_metrics_repo.get_latest_snapshot = AsyncMock(return_value=None)
        mock_metrics_repo.insert_snapshot = AsyncMock()

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
            "mr_mod": patch("app.storage.repo_metrics.MetricsRepo"),
            "mr_pkg": patch("app.storage.MetricsRepo"),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory
            for k in ("er_mod", "er_pkg"):
                mocks[k].return_value = mock_events_repo
            for k in ("mr_mod", "mr_pkg"):
                mocks[k].return_value = mock_metrics_repo

            result = await run_bot_clicks_aggregator()

            assert result["processed"] == 4
            assert result["posts_updated"] == 2

            # Should have inserted snapshots for p1 and p2
            assert mock_metrics_repo.insert_snapshot.call_count == 2

            # Find the call for p1 and verify count=3
            calls = mock_metrics_repo.insert_snapshot.call_args_list
            p1_call = next(
                c for c in calls if c.kwargs.get("post_id") == "p1"
            )
            assert p1_call.kwargs["bot_clicks"] == 3

            p2_call = next(
                c for c in calls if c.kwargs.get("post_id") == "p2"
            )
            assert p2_call.kwargs["bot_clicks"] == 1
        finally:
            for p in patches.values():
                p.stop()


# ---------------------------------------------------------------------------
# 5. test_metrics_ingest_requires_admin_token
# ---------------------------------------------------------------------------


class TestMetricsIngestAuth:
    """POST /admin/metrics/ingest must require a valid ADMIN_TOKEN."""

    @pytest.mark.asyncio
    async def test_rejects_without_token(self):
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/metrics/ingest",
                json={
                    "post_id": "p1",
                    "captured_at": "2026-02-06T12:00:00",
                    "views": 100,
                },
            )
            assert resp.status_code in (401, 503)

    @pytest.mark.asyncio
    async def test_rejects_wrong_token(self):
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/admin/metrics/ingest",
                json={
                    "post_id": "p1",
                    "captured_at": "2026-02-06T12:00:00",
                },
                headers={"Authorization": "Bearer wrong-token"},
            )
            # Either 403 (bad token) or 503 (no ADMIN_TOKEN configured)
            assert resp.status_code in (403, 503)

"""Tests for the schedule bandit (post timing A/B testing).

Covers:
1. Schedule presets structure validation
2. get_all_unique_slots collects all slots
3. slot_in_schedule correctly gates execution
4. Bandit picks random when no scores exist
5. Bandit exploits best schedule with scores
6. run_publish_post skips slot not in active schedule
7. run_publish_post stores schedule_id in meta_json
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Schedule presets structure
# ---------------------------------------------------------------------------


class TestSchedulePresetsStructure:
    """Validate schedule presets are well-formed."""

    def test_all_presets_have_slots(self):
        from app.jobs.schedule_presets import SCHEDULE_PRESETS

        assert len(SCHEDULE_PRESETS) >= 3
        for name, preset in SCHEDULE_PRESETS.items():
            assert len(preset.slots) >= 1, f"{name} has no slots"
            assert preset.description, f"{name} has no description"

    def test_slots_are_valid_times(self):
        from app.jobs.schedule_presets import SCHEDULE_PRESETS

        for name, preset in SCHEDULE_PRESETS.items():
            for slot in preset.slots:
                parts = slot.split(":")
                assert len(parts) == 2, f"{name}: invalid slot format '{slot}'"
                h, m = int(parts[0]), int(parts[1])
                assert 0 <= h <= 23, f"{name}: invalid hour in '{slot}'"
                assert 0 <= m <= 59, f"{name}: invalid minute in '{slot}'"

    def test_presets_have_variety(self):
        """Different presets should have different slot counts."""
        from app.jobs.schedule_presets import SCHEDULE_PRESETS

        slot_counts = {len(p.slots) for p in SCHEDULE_PRESETS.values()}
        assert len(slot_counts) >= 2, "All presets have the same number of slots"


# ---------------------------------------------------------------------------
# 2. get_all_unique_slots
# ---------------------------------------------------------------------------


class TestGetAllUniqueSlots:
    def test_returns_sorted_unique(self):
        from app.jobs.schedule_presets import get_all_unique_slots, SCHEDULE_PRESETS

        slots = get_all_unique_slots()
        # Should be sorted
        assert slots == sorted(slots)
        # Should be unique
        assert len(slots) == len(set(slots))
        # Should contain slots from presets
        for preset in SCHEDULE_PRESETS.values():
            for s in preset.slots:
                assert s in slots

    def test_returns_nonempty(self):
        from app.jobs.schedule_presets import get_all_unique_slots

        assert len(get_all_unique_slots()) > 0


# ---------------------------------------------------------------------------
# 3. slot_in_schedule
# ---------------------------------------------------------------------------


class TestSlotInSchedule:
    def test_slot_present(self):
        from app.jobs.schedule_presets import slot_in_schedule

        assert slot_in_schedule("09:30", "morning_evening") is True
        assert slot_in_schedule("19:30", "morning_evening") is True

    def test_slot_absent(self):
        from app.jobs.schedule_presets import slot_in_schedule

        assert slot_in_schedule("13:00", "morning_evening") is False
        assert slot_in_schedule("21:00", "morning_evening") is False

    def test_unknown_schedule(self):
        from app.jobs.schedule_presets import slot_in_schedule

        assert slot_in_schedule("09:30", "nonexistent_schedule") is False

    def test_once_evening(self):
        from app.jobs.schedule_presets import slot_in_schedule

        assert slot_in_schedule("19:30", "once_evening") is True
        assert slot_in_schedule("09:30", "once_evening") is False


# ---------------------------------------------------------------------------
# 4. Bandit picks random when no scores
# ---------------------------------------------------------------------------


class TestBanditNoScores:
    @pytest.mark.asyncio
    async def test_random_pick_when_no_scores(self):
        from app.jobs.schedule_presets import pick_schedule_bandit, SCHEDULE_PRESETS

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []  # No scored posts
        mock_session.execute = AsyncMock(return_value=mock_result)

        schedule_id = await pick_schedule_bandit(mock_session)
        assert schedule_id in SCHEDULE_PRESETS


# ---------------------------------------------------------------------------
# 5. Bandit exploits best schedule
# ---------------------------------------------------------------------------


class TestBanditExploitsBest:
    @pytest.mark.asyncio
    async def test_exploit_picks_best(self):
        """With EXPLOIT_RATE=1.0, should always pick the highest scoring schedule."""
        from app.jobs.schedule_presets import pick_schedule_bandit, SCHEDULE_PRESETS

        # Mock scored posts: "peak_hours" has the best average
        mock_rows = [
            ("p1", json.dumps({"schedule_id": "morning_evening"}), 10.0),
            ("p2", json.dumps({"schedule_id": "morning_evening"}), 15.0),
            ("p3", json.dumps({"schedule_id": "peak_hours"}), 50.0),
            ("p4", json.dumps({"schedule_id": "peak_hours"}), 60.0),
            ("p5", json.dumps({"schedule_id": "three_times"}), 20.0),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("app.jobs.schedule_presets.EXPLOIT_RATE", 1.0):
            schedule_id = await pick_schedule_bandit(mock_session)
            assert schedule_id == "peak_hours"

    @pytest.mark.asyncio
    async def test_explore_picks_non_best(self):
        """With EXPLOIT_RATE=0.0, should always pick a non-best schedule."""
        from app.jobs.schedule_presets import pick_schedule_bandit

        mock_rows = [
            ("p1", json.dumps({"schedule_id": "peak_hours"}), 50.0),
            ("p2", json.dumps({"schedule_id": "three_times"}), 20.0),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("app.jobs.schedule_presets.EXPLOIT_RATE", 0.0):
            schedule_id = await pick_schedule_bandit(mock_session)
            assert schedule_id != "peak_hours"


# ---------------------------------------------------------------------------
# 6. run_publish_post skips slot not in active schedule
# ---------------------------------------------------------------------------


class TestPublishPostScheduleGating:
    @pytest.mark.asyncio
    async def test_skips_slot_not_in_schedule(self):
        """If schedule bandit picks a schedule that doesn't include this
        slot_time, the job should return early with error='slot_not_in_schedule'."""
        from app.jobs.publish_posts import run_publish_post

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session_ctx)

        mock_events_repo = AsyncMock()
        mock_events_repo.log_event = AsyncMock()

        patches = {
            "config": patch("app.jobs.publish_posts.config"),
            "sf_db": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
            "er_mod": patch("app.storage.repo_events.EventsRepo"),
            "er_pkg": patch("app.storage.EventsRepo"),
            # Bandit always returns "once_evening" (only has 19:30)
            "bandit": patch(
                "app.jobs.schedule_presets.pick_schedule_bandit",
                new_callable=AsyncMock,
                return_value="once_evening",
            ),
        }

        mocks = {k: p.start() for k, p in patches.items()}
        try:
            mocks["config"].channel_post_enabled = True
            mocks["config"].channel_id = "-100123"
            mocks["config"].bot_username = "testbot"

            for k in ("sf_db", "sf_pkg"):
                mocks[k].return_value = mock_factory
            for k in ("er_mod", "er_pkg"):
                mocks[k].return_value = mock_events_repo

            # Call with slot_time="09:30" which is NOT in "once_evening"
            result = await run_publish_post(slot_index=0, slot_time="09:30")

            assert result.ok is False
            assert result.error == "slot_not_in_schedule"
        finally:
            for p in patches.values():
                p.stop()


# ---------------------------------------------------------------------------
# 7. run_publish_post stores schedule_id in meta_json
# ---------------------------------------------------------------------------


class TestPublishPostStoresScheduleId:
    @pytest.mark.asyncio
    async def test_schedule_id_in_meta(self):
        """When a post is published, schedule_id must appear in meta_json."""
        from app.jobs.publish_posts import run_publish_post

        mock_msg = MagicMock()
        mock_msg.message_id = 42

        mock_generated = MagicMock()
        mock_generated.text = "Test post"
        mock_generated.meta_json = json.dumps({"items": [], "format_id": "poll"})
        mock_generated.used_llm = False
        mock_generated.lint_passed = True
        mock_generated.poster_url = None

        mock_posts_repo = AsyncMock()
        mock_posts_repo.list_recent_posts = AsyncMock(return_value=[])
        mock_posts_repo.create_post = AsyncMock()

        mock_events_repo = AsyncMock()
        mock_events_repo.log_event = AsyncMock()

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
            "format_bandit": patch(
                "app.jobs.publish_posts._pick_format_bandit",
                new_callable=AsyncMock,
                return_value="poll",
            ),
            "schedule_bandit": patch(
                "app.jobs.schedule_presets.pick_schedule_bandit",
                new_callable=AsyncMock,
                return_value="three_times",
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
            for k in ("er_mod", "er_pkg"):
                mocks[k].return_value = mock_events_repo
            for k in ("ab_mod", "ab_pkg"):
                mocks[k].return_value = mock_ab_repo

            # slot_time="13:00" is in "three_times" preset
            result = await run_publish_post(slot_index=1, slot_time="13:00")

            assert result.ok is True

            # Check meta_json for schedule_id
            call_kwargs = mock_posts_repo.create_post.call_args.kwargs
            saved_meta = json.loads(call_kwargs["meta_json"])
            assert saved_meta["schedule_id"] == "three_times"

            # Check event payload also has schedule_id
            event_calls = mock_events_repo.log_event.call_args_list
            published_call = next(
                c for c in event_calls
                if c.kwargs.get("event_name") == "post_published"
            )
            assert published_call.kwargs["payload"]["schedule_id"] == "three_times"
        finally:
            for p in patches.values():
                p.stop()

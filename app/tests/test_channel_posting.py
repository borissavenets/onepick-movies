"""Tests for channel auto-posting job.

Covers:
- Format rotation cycles through ROTATION_ORDER
- bot_teaser max once per day
- Post saved to DB with meta
- Job skips when disabled
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.jobs.channel_posting import (
    ROTATION_ORDER,
    PostResult,
    _pick_format,
    run_channel_post,
)


# ---------------------------------------------------------------------------
# 1. test_format_rotation_cycles_through_formats
# ---------------------------------------------------------------------------


class TestFormatRotation:
    """Test that _pick_format cycles through ROTATION_ORDER."""

    def test_first_post_of_day(self):
        """First post should be the first format in rotation."""
        fmt = _pick_format([])
        assert fmt == ROTATION_ORDER[0]

    def test_cycles_through_order(self):
        """Each subsequent post picks the next format in order."""
        for i in range(len(ROTATION_ORDER)):
            fake_posts = [MagicMock() for _ in range(i)]
            fmt = _pick_format(fake_posts)
            expected = ROTATION_ORDER[i]
            # bot_teaser may be skipped if a teaser already present,
            # but with empty format_ids on mocks it won't match
            if expected == "bot_teaser":
                # mock posts don't have format_id="bot_teaser"
                assert fmt == expected
            else:
                assert fmt == expected

    def test_wraps_around(self):
        """After full cycle, rotation wraps to start."""
        fake_posts = [MagicMock() for _ in range(len(ROTATION_ORDER))]
        fmt = _pick_format(fake_posts)
        assert fmt == ROTATION_ORDER[0]


# ---------------------------------------------------------------------------
# 2. test_bot_teaser_max_once_per_day
# ---------------------------------------------------------------------------


class TestBotTeaserLimit:
    """Test that bot_teaser is only used once per day."""

    def test_bot_teaser_skipped_if_already_posted(self):
        """If bot_teaser was already posted today, it's skipped."""
        # Find the index of bot_teaser in rotation
        teaser_idx = ROTATION_ORDER.index("bot_teaser")

        # Create fake posts: enough to reach bot_teaser slot
        fake_posts = []
        for i in range(teaser_idx):
            p = MagicMock()
            p.format_id = ROTATION_ORDER[i]
            fake_posts.append(p)

        # First time at teaser slot — should pick bot_teaser
        fmt = _pick_format(fake_posts)
        assert fmt == "bot_teaser"

        # Now add a bot_teaser post to the list
        teaser_post = MagicMock()
        teaser_post.format_id = "bot_teaser"
        fake_posts.append(teaser_post)

        # We're now at index teaser_idx+1 in rotation but the count
        # puts us past teaser; to test the skip, let's wrap around
        # to land on bot_teaser again
        while len(fake_posts) % len(ROTATION_ORDER) != teaser_idx:
            p = MagicMock()
            p.format_id = "filler"
            fake_posts.append(p)

        fmt2 = _pick_format(fake_posts)
        # Should NOT be bot_teaser because one already exists today
        assert fmt2 != "bot_teaser"


# ---------------------------------------------------------------------------
# 3. test_post_saved_to_db_with_meta
# ---------------------------------------------------------------------------


class TestPostSavedToDB:
    """Test that run_channel_post persists post and event to DB."""

    @pytest.mark.asyncio
    async def test_post_saved_to_db_with_meta(self):
        """Successful post is saved via PostsRepo and EventsRepo."""
        mock_msg = MagicMock()
        mock_msg.message_id = 42

        mock_generated = MagicMock()
        mock_generated.text = "Тестовий пост"
        mock_generated.meta_json = '{"format_id": "one_pick_emotion"}'
        mock_generated.used_llm = False
        mock_generated.lint_passed = True

        mock_posts_repo = AsyncMock()
        mock_events_repo = AsyncMock()

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session_ctx

        call_count = 0

        def factory_side_effect():
            nonlocal call_count
            call_count += 1
            return mock_session_ctx

        mock_session_factory.side_effect = factory_side_effect

        # Patch at the package level so late `from app.X import Y` picks up mocks
        patches = {
            "config": patch("app.jobs.channel_posting.config"),
            "send": patch("app.bot.sender.safe_send_message", new_callable=AsyncMock),
            "sf": patch("app.storage.db.get_session_factory"),
            "sf_pkg": patch("app.storage.get_session_factory"),
            "posts_repo_cls": patch("app.storage.PostsRepo"),
            "posts_repo_mod": patch("app.storage.repo_posts.PostsRepo"),
            "events_repo_cls": patch("app.storage.EventsRepo"),
            "events_repo_mod": patch("app.storage.repo_events.EventsRepo"),
            "gen": patch("app.content.generator.generate_post", new_callable=AsyncMock),
            "bot": patch("app.main.bot"),
        }

        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()

        try:
            mocks["config"].channel_post_enabled = True
            mocks["config"].channel_id = "-1001234567890"

            # Both session factory patches return the same mock
            mocks["sf"].return_value = mock_session_factory
            mocks["sf_pkg"].return_value = mock_session_factory

            mocks["send"].return_value = mock_msg
            mocks["gen"].return_value = mock_generated

            # Both PostsRepo patches return the same mock instance
            for key in ("posts_repo_cls", "posts_repo_mod"):
                mocks[key].return_value = mock_posts_repo
            mock_posts_repo.list_recent_posts = AsyncMock(return_value=[])
            mock_posts_repo.create_post = AsyncMock()

            for key in ("events_repo_cls", "events_repo_mod"):
                mocks[key].return_value = mock_events_repo
            mock_events_repo.log_event = AsyncMock()

            result = await run_channel_post(slot_index=0)

            assert result.ok is True
            assert result.post_id == "42"

            mock_posts_repo.create_post.assert_called_once()
            call_kwargs = mock_posts_repo.create_post.call_args
            assert call_kwargs.kwargs["post_id"] == "42"
            assert call_kwargs.kwargs["text"] == "Тестовий пост"

            mock_events_repo.log_event.assert_called_once()
            event_kwargs = mock_events_repo.log_event.call_args
            assert event_kwargs.kwargs["event_name"] == "post_published"
            assert event_kwargs.kwargs["post_id"] == "42"
        finally:
            for p in patches.values():
                p.stop()


# ---------------------------------------------------------------------------
# 4. test_job_skips_when_disabled
# ---------------------------------------------------------------------------


class TestJobSkipsWhenDisabled:
    """Test that the job does nothing when posting is disabled."""

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        """Job returns immediately with error when disabled."""
        with patch("app.jobs.channel_posting.config") as mock_config:
            mock_config.channel_post_enabled = False

            result = await run_channel_post()

            assert result.ok is False
            assert result.error == "posting_disabled"

    @pytest.mark.asyncio
    async def test_skips_when_channel_id_missing(self):
        """Job returns immediately when CHANNEL_ID is empty."""
        with patch("app.jobs.channel_posting.config") as mock_config:
            mock_config.channel_post_enabled = True
            mock_config.channel_id = ""

            result = await run_channel_post()

            assert result.ok is False
            assert result.error == "channel_id_missing"

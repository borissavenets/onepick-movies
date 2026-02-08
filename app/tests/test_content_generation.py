"""Tests for content generation pipeline.

Covers:
- Style lint limits
- Banned words detection (UA)
- Generator fallback when LLM disabled
- Generator respects hook and body length
- Repeat avoidance (same item not used within 60 days)
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.content.style_lint import lint_post, fix_common_issues, truncate_to_limits
from app.content.templates import render_fallback


# ---------------------------------------------------------------------------
# 1. test_style_lint_limits
# ---------------------------------------------------------------------------

class TestStyleLintLimits:
    """Test that style lint enforces all limits."""

    def test_hook_too_long(self):
        """First line exceeding 90 chars triggers error."""
        long_hook = "А" * 91
        text = f"{long_hook}\n\nКороткий текст."
        result = lint_post(text)
        assert not result.passed
        violations = [v.rule for v in result.violations]
        assert "hook_length" in violations

    def test_hook_within_limit(self):
        """First line within 90 chars passes."""
        hook = "А" * 90
        text = f"{hook}\n\nКороткий текст."
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "hook_length" not in violations

    def test_body_too_long(self):
        """Total text exceeding 600 chars triggers error."""
        text = "Хук\n\n" + "Текст " * 120  # well over 600 chars
        result = lint_post(text)
        assert not result.passed
        violations = [v.rule for v in result.violations]
        assert "body_length" in violations

    def test_body_within_limit(self):
        """Text within 600 chars passes body check."""
        text = "Короткий хук\n\nКороткий текст."
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "body_length" not in violations

    def test_too_many_lines(self):
        """More than 6 non-empty lines triggers error."""
        lines = [f"Рядок {i}" for i in range(8)]
        text = "\n".join(lines)
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "max_lines" in violations

    def test_six_lines_ok(self):
        """Exactly 6 non-empty lines passes."""
        lines = [f"Рядок {i}" for i in range(6)]
        text = "\n".join(lines)
        result = lint_post(text)
        violations = [v.rule for v in result.violations if v.severity == "error"]
        assert "max_lines" not in [v.rule for v in violations]

    def test_double_blank_lines_warning(self):
        """Double blank lines produce warning."""
        text = "Хук\n\n\nТекст."
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "double_blank" in violations

    def test_fix_common_issues_removes_double_blanks(self):
        """fix_common_issues removes double blank lines."""
        text = "Рядок 1\n\n\nРядок 2"
        fixed = fix_common_issues(text)
        assert "\n\n\n" not in fixed
        assert "Рядок 1" in fixed
        assert "Рядок 2" in fixed

    def test_truncate_to_limits(self):
        """truncate_to_limits respects body max chars."""
        text = "Хук.\n\n" + "Слово " * 200  # way over 600
        truncated = truncate_to_limits(text)
        assert len(truncated) <= 600


# ---------------------------------------------------------------------------
# 2. test_banned_words_detection (UA)
# ---------------------------------------------------------------------------

class TestBannedWordsDetection:
    """Test banned and spoiler word detection."""

    def test_banned_word_detected(self):
        """Banned words are detected case-insensitively."""
        text = "Цей фільм — справжній шедевр кінематографу."
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "banned_word" in violations

    def test_banned_word_imdb(self):
        """IMDb is detected as banned word."""
        text = "Короткий хук\n\nОцінка на IMDb — 9.1."
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "banned_word" in violations

    def test_banned_word_rating(self):
        """'рейтинг' is detected as banned word."""
        text = "Короткий хук\n\nРейтинг цього фільму вражає."
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "banned_word" in violations

    def test_banned_word_top(self):
        """'топ' is detected as banned word."""
        text = "Топ фільмів для вечора"
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "banned_word" in violations

    def test_spoiler_word_detected(self):
        """Spoiler words are detected."""
        text = "Короткий хук\n\nТвіст у кінці вражає."
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "spoiler_word" in violations

    def test_spoiler_word_ending(self):
        """English spoiler word 'ending' detected."""
        text = "Короткий хук\n\nThe ending is surprising."
        result = lint_post(text)
        violations = [v.rule for v in result.violations]
        assert "spoiler_word" in violations

    def test_clean_text_passes(self):
        """Text without banned/spoiler words passes."""
        text = "Коли хочеться тиші\n\nФільм для вечора. Спокійний і вдумливий."
        result = lint_post(text)
        violations = [v.rule for v in result.violations if v.severity == "error"]
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# 3. test_generator_fallback_when_llm_disabled
# ---------------------------------------------------------------------------

class TestGeneratorFallback:
    """Test that generator falls back to templates when LLM is disabled."""

    @pytest.mark.asyncio
    async def test_fallback_one_pick_emotion(self):
        """one_pick_emotion generates valid fallback without LLM."""
        from app.content.generator import generate_post
        from app.content.selector import SelectedItem

        mock_item = SelectedItem(
            item_id="test-1",
            title="Тестовий Фільм",
            item_type="movie",
            overview="Це тестовий опис фільму.",
            tags={"mood": ["light"], "pace": ["slow"], "tone": ["warm"]},
            rating=7.5,
        )

        with patch("app.content.generator.select_for_one_pick", new_callable=AsyncMock) as mock_select, \
             patch("app.content.generator.config") as mock_config:
            mock_select.return_value = mock_item
            mock_config.llm_enabled = False
            mock_config.post_hook_max_chars = 90
            mock_config.post_body_max_chars = 600
            mock_config.post_language = "uk"
            mock_config.bot_username = "TestBot"
            mock_config.cta_rate = 1.0  # always include CTA
            mock_config.banned_words = ["топ", "imdb", "рейтинг", "найкращий", "must-watch", "шедевр"]
            mock_config.spoiler_words = ["твіст", "кінцівка"]

            # Need a real session mock
            session = AsyncMock()
            result = await generate_post(
                session=session,
                format_id="one_pick_emotion",
                hypothesis_id="h1",
                variant_id="v1",
            )

            assert result.text != ""
            assert result.used_llm is False
            assert result.format_id == "one_pick_emotion"
            assert "Тестовий Фільм" in result.text

    @pytest.mark.asyncio
    async def test_fallback_bot_teaser(self):
        """bot_teaser generates valid fallback without LLM."""
        from app.content.generator import generate_post

        with patch("app.content.generator.config") as mock_config:
            mock_config.llm_enabled = False
            mock_config.post_hook_max_chars = 90
            mock_config.post_body_max_chars = 600
            mock_config.post_language = "uk"
            mock_config.bot_username = "TestBot"
            mock_config.cta_rate = 1.0
            mock_config.banned_words = []
            mock_config.spoiler_words = []

            session = AsyncMock()
            result = await generate_post(
                session=session,
                format_id="bot_teaser",
                hypothesis_id="h1",
                variant_id="v1",
            )

            assert result.text != ""
            assert result.used_llm is False
            assert result.format_id == "bot_teaser"


# ---------------------------------------------------------------------------
# 4. test_generator_respects_hook_and_body_length
# ---------------------------------------------------------------------------

class TestGeneratorRespectsLimits:
    """Test that generated content respects length limits."""

    def test_fallback_one_pick_within_limits(self):
        """Fallback template for one_pick_emotion fits within limits."""
        items = [{
            "title": "Тестовий Фільм",
            "type": "movie",
            "mood": ["light"],
            "pace": ["slow"],
            "tone": ["warm"],
        }]
        cta = "Підібрати за 3 питання \u2192 https://t.me/TestBot?start=post_abc_vv1"
        text = render_fallback("one_pick_emotion", items, cta)

        result = lint_post(text)
        # Check hook length
        first_line = text.strip().split("\n")[0]
        assert len(first_line) <= 90, f"Hook too long: {len(first_line)} chars"

    def test_fallback_if_liked_within_limits(self):
        """Fallback template for if_liked_x_then_y fits within limits."""
        items = [
            {
                "title": "Inception",
                "type": "movie",
                "mood": ["heavy"],
                "pace": ["fast"],
                "tone": ["dark"],
            },
            {
                "title": "Interstellar",
                "type": "movie",
                "mood": ["heavy"],
                "pace": ["slow"],
                "tone": ["warm"],
            },
        ]
        cta = "Підібрати за 3 питання \u2192 https://t.me/TestBot?start=post_abc_vv1"
        text = render_fallback("if_liked_x_then_y", items, cta)

        assert len(text) <= 600, f"Body too long: {len(text)} chars"

    def test_fallback_bot_teaser_within_limits(self):
        """Fallback template for bot_teaser fits within limits."""
        cta = "Підібрати за 3 питання \u2192 https://t.me/TestBot?start=post_abc_vv1"
        text = render_fallback("bot_teaser", [], cta)

        assert len(text) <= 600
        first_line = text.strip().split("\n")[0]
        assert len(first_line) <= 90

    def test_all_fallback_formats_within_body_limit(self):
        """All fallback formats produce text within body limit."""
        items_movie = [{
            "title": "Test Movie",
            "type": "movie",
            "mood": ["light"],
            "pace": ["slow"],
            "tone": ["warm"],
        }]
        items_pair = [
            items_movie[0],
            {
                "title": "Test Movie 2",
                "type": "movie",
                "mood": ["light"],
                "pace": ["fast"],
                "tone": ["funny"],
            },
        ]
        cta = "Підібрати за 3 питання \u2192 https://t.me/Bot?start=x"

        for fmt_id, items_for_fmt in [
            ("one_pick_emotion", items_movie),
            ("if_liked_x_then_y", items_pair),
            ("fact_then_pick", items_movie),
            ("bot_teaser", []),
        ]:
            text = render_fallback(fmt_id, items_for_fmt, cta)
            assert len(text) <= 600, f"{fmt_id}: body too long ({len(text)})"


# ---------------------------------------------------------------------------
# 5. test_repeat_avoidance
# ---------------------------------------------------------------------------

class TestRepeatAvoidance:
    """Test that items are not repeated within avoidance window."""

    @pytest.mark.asyncio
    async def test_recently_posted_items_excluded(self):
        """Items posted recently are excluded from selection."""
        from app.content.selector import get_recently_posted_item_ids
        from app.storage.models import Post

        # Create mock posts with meta_json containing item IDs
        mock_post_1 = Post(
            post_id="p1",
            format_id="one_pick_emotion",
            hypothesis_id="h1",
            variant_id="v1",
            text="test",
            meta_json=json.dumps({"items": ["item-1", "item-2"]}),
            published_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        mock_post_2 = Post(
            post_id="p2",
            format_id="fact_then_pick",
            hypothesis_id="h2",
            variant_id="v1",
            text="test2",
            meta_json=json.dumps({"items": ["item-3"]}),
            published_at=datetime.now(timezone.utc) - timedelta(days=5),
        )

        session = AsyncMock()
        with patch("app.content.selector.PostsRepo") as MockPostsRepo:
            mock_repo = AsyncMock()
            mock_repo.list_recent_posts.return_value = [mock_post_1, mock_post_2]
            MockPostsRepo.return_value = mock_repo

            excluded = await get_recently_posted_item_ids(session, days=60)

            assert "item-1" in excluded
            assert "item-2" in excluded
            assert "item-3" in excluded

    @pytest.mark.asyncio
    async def test_old_posts_not_excluded(self):
        """Items posted beyond the avoidance window are not excluded."""
        from app.content.selector import get_recently_posted_item_ids
        from app.storage.models import Post

        # Post older than 60 days
        old_post = Post(
            post_id="p-old",
            format_id="one_pick_emotion",
            hypothesis_id="h1",
            variant_id="v1",
            text="old test",
            meta_json=json.dumps({"items": ["old-item"]}),
            published_at=datetime.now(timezone.utc) - timedelta(days=90),
        )

        session = AsyncMock()
        with patch("app.content.selector.PostsRepo") as MockPostsRepo:
            mock_repo = AsyncMock()
            mock_repo.list_recent_posts.return_value = [old_post]
            MockPostsRepo.return_value = mock_repo

            excluded = await get_recently_posted_item_ids(session, days=60)

            assert "old-item" not in excluded

    @pytest.mark.asyncio
    async def test_meta_json_without_items_key(self):
        """Posts without items in meta_json don't cause errors."""
        from app.content.selector import get_recently_posted_item_ids
        from app.storage.models import Post

        post = Post(
            post_id="p-no-items",
            format_id="poll",
            hypothesis_id="h1",
            variant_id="v1",
            text="poll text",
            meta_json="{}",
            published_at=datetime.now(timezone.utc) - timedelta(days=5),
        )

        session = AsyncMock()
        with patch("app.content.selector.PostsRepo") as MockPostsRepo:
            mock_repo = AsyncMock()
            mock_repo.list_recent_posts.return_value = [post]
            MockPostsRepo.return_value = mock_repo

            excluded = await get_recently_posted_item_ids(session, days=60)

            assert len(excluded) == 0

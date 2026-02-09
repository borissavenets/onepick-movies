"""Tests for poster combining utility."""

import os
import tempfile
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.content.poster_combine import combine_posters, _resize_to_height


def _make_test_image(width: int, height: int, color: str = "red") -> Image.Image:
    """Create a simple test image."""
    return Image.new("RGB", (width, height), color=color)


def _image_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class TestResizeToHeight:
    """Test the _resize_to_height helper."""

    def test_already_correct_height(self):
        img = _make_test_image(500, 1024)
        result = _resize_to_height(img, 1024)
        assert result.height == 1024
        assert result.width == 500

    def test_resize_down(self):
        img = _make_test_image(500, 2048)
        result = _resize_to_height(img, 1024)
        assert result.height == 1024
        assert result.width == 250

    def test_resize_up(self):
        img = _make_test_image(200, 512)
        result = _resize_to_height(img, 1024)
        assert result.height == 1024
        assert result.width == 400


class TestCombinePosters:
    """Test the combine_posters async function."""

    @pytest.mark.asyncio
    async def test_combine_local_files(self):
        """Combine two local poster files."""
        img_a = _make_test_image(500, 1024, "red")
        img_b = _make_test_image(500, 1024, "blue")

        tmp_a = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_b = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            img_a.save(tmp_a, format="PNG")
            img_b.save(tmp_b, format="PNG")
            tmp_a.close()
            tmp_b.close()

            result_path = await combine_posters(tmp_a.name, tmp_b.name)

            assert result_path is not None
            assert os.path.isfile(result_path)

            combined = Image.open(result_path)
            assert combined.height == 1024
            # 500 + 4 (divider) + 500
            assert combined.width == 1004
            combined.close()

            os.unlink(result_path)
        finally:
            os.unlink(tmp_a.name)
            os.unlink(tmp_b.name)

    @pytest.mark.asyncio
    async def test_combine_different_heights(self):
        """Posters with different heights get resized to match."""
        img_a = _make_test_image(500, 1536, "red")
        img_b = _make_test_image(400, 800, "blue")

        tmp_a = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp_b = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            img_a.save(tmp_a, format="PNG")
            img_b.save(tmp_b, format="PNG")
            tmp_a.close()
            tmp_b.close()

            result_path = await combine_posters(tmp_a.name, tmp_b.name)

            assert result_path is not None
            combined = Image.open(result_path)
            assert combined.height == 1024
            combined.close()

            os.unlink(result_path)
        finally:
            os.unlink(tmp_a.name)
            os.unlink(tmp_b.name)

    @pytest.mark.asyncio
    async def test_combine_urls(self):
        """Combine two posters fetched from URLs."""
        img_a = _make_test_image(500, 1024, "red")
        img_b = _make_test_image(500, 1024, "blue")

        mock_response_a = AsyncMock()
        mock_response_a.content = _image_to_bytes(img_a)
        mock_response_a.raise_for_status = lambda: None

        mock_response_b = AsyncMock()
        mock_response_b.content = _image_to_bytes(img_b)
        mock_response_b.raise_for_status = lambda: None

        async def mock_get(url, **kwargs):
            if "poster_a" in url:
                return mock_response_a
            return mock_response_b

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.content.poster_combine.httpx.AsyncClient", return_value=mock_client):
            result_path = await combine_posters(
                "https://example.com/poster_a.jpg",
                "https://example.com/poster_b.jpg",
            )

            assert result_path is not None
            assert os.path.isfile(result_path)
            os.unlink(result_path)

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        """Returns None when a poster can't be fetched."""
        result = await combine_posters(
            "/nonexistent/path/a.jpg",
            "/nonexistent/path/b.jpg",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_generator_uses_combined_poster(self):
        """generate_post combines posters for 2-item formats."""
        from app.content.generator import generate_post
        from app.content.selector import SelectedItem

        item_a = SelectedItem(
            item_id="a1",
            title="Film A",
            item_type="movie",
            overview="Overview A",
            tags={"mood": ["dark"], "pace": ["fast"], "tone": ["tense"]},
            rating=8.0,
            poster_url="https://example.com/a.jpg",
        )
        item_b = SelectedItem(
            item_id="b1",
            title="Film B",
            item_type="movie",
            overview="Overview B",
            tags={"mood": ["dark"], "pace": ["slow"], "tone": ["warm"]},
            rating=7.5,
            poster_url="https://example.com/b.jpg",
        )

        with patch("app.content.generator.select_for_versus", new_callable=AsyncMock) as mock_sel, \
             patch("app.content.generator.combine_posters", new_callable=AsyncMock) as mock_combine, \
             patch("app.content.generator.config") as mock_config:
            mock_sel.return_value = (item_a, item_b)
            mock_combine.return_value = "/tmp/combined.jpg"
            mock_config.llm_enabled = False
            mock_config.post_hook_max_chars = 90
            mock_config.post_body_max_chars = 600
            mock_config.post_language = "uk"
            mock_config.bot_username = "TestBot"
            mock_config.cta_rate = 0.0
            mock_config.banned_words = []
            mock_config.spoiler_words = []

            session = AsyncMock()
            result = await generate_post(
                session=session,
                format_id="versus",
                hypothesis_id="h1",
                variant_id="v1",
            )

            mock_combine.assert_called_once_with(
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
            )
            assert result.poster_url == "/tmp/combined.jpg"

    @pytest.mark.asyncio
    async def test_generator_fallback_when_combine_fails(self):
        """Falls back to first poster when combine returns None."""
        from app.content.generator import generate_post
        from app.content.selector import SelectedItem

        item_a = SelectedItem(
            item_id="a1",
            title="Film A",
            item_type="movie",
            overview="Overview A",
            tags={"mood": ["dark"], "pace": ["fast"], "tone": ["tense"]},
            rating=8.0,
            poster_url="https://example.com/a.jpg",
        )
        item_b = SelectedItem(
            item_id="b1",
            title="Film B",
            item_type="movie",
            overview="Overview B",
            tags={"mood": ["dark"], "pace": ["slow"], "tone": ["warm"]},
            rating=7.5,
            poster_url="https://example.com/b.jpg",
        )

        with patch("app.content.generator.select_for_if_liked", new_callable=AsyncMock) as mock_sel, \
             patch("app.content.generator.combine_posters", new_callable=AsyncMock) as mock_combine, \
             patch("app.content.generator.config") as mock_config:
            mock_sel.return_value = (item_a, item_b)
            mock_combine.return_value = None  # combine fails
            mock_config.llm_enabled = False
            mock_config.post_hook_max_chars = 90
            mock_config.post_body_max_chars = 600
            mock_config.post_language = "uk"
            mock_config.bot_username = "TestBot"
            mock_config.cta_rate = 0.0
            mock_config.banned_words = []
            mock_config.spoiler_words = []

            session = AsyncMock()
            result = await generate_post(
                session=session,
                format_id="if_liked_x_then_y",
                hypothesis_id="h1",
                variant_id="v1",
            )

            assert result.poster_url == "https://example.com/a.jpg"

    @pytest.mark.asyncio
    async def test_generator_single_poster_when_second_missing(self):
        """Uses first poster when second item has no poster_url."""
        from app.content.generator import generate_post
        from app.content.selector import SelectedItem

        item_a = SelectedItem(
            item_id="a1",
            title="Film A",
            item_type="movie",
            overview="Overview A",
            tags={"mood": ["dark"], "pace": ["fast"], "tone": ["tense"]},
            rating=8.0,
            poster_url="https://example.com/a.jpg",
        )
        item_b = SelectedItem(
            item_id="b1",
            title="Film B",
            item_type="movie",
            overview="Overview B",
            tags={"mood": ["dark"], "pace": ["slow"], "tone": ["warm"]},
            rating=7.5,
            poster_url=None,  # no poster
        )

        with patch("app.content.generator.select_for_versus", new_callable=AsyncMock) as mock_sel, \
             patch("app.content.generator.combine_posters", new_callable=AsyncMock) as mock_combine, \
             patch("app.content.generator.config") as mock_config:
            mock_sel.return_value = (item_a, item_b)
            mock_config.llm_enabled = False
            mock_config.post_hook_max_chars = 90
            mock_config.post_body_max_chars = 600
            mock_config.post_language = "uk"
            mock_config.bot_username = "TestBot"
            mock_config.cta_rate = 0.0
            mock_config.banned_words = []
            mock_config.spoiler_words = []

            session = AsyncMock()
            result = await generate_post(
                session=session,
                format_id="versus",
                hypothesis_id="h1",
                variant_id="v1",
            )

            # combine_posters should NOT be called when second poster is None
            mock_combine.assert_not_called()
            assert result.poster_url == "https://example.com/a.jpg"

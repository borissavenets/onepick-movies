"""Tests for /credits command."""

import os

os.environ["BOT_TOKEN"] = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
os.environ["BOT_MODE"] = "polling"


def test_credits_message_contains_tmdb_disclaimer():
    """Test that CREDITS_MESSAGE contains the required TMDB disclaimer."""
    from app.bot.messages import CREDITS_MESSAGE

    assert "TMDB" in CREDITS_MESSAGE
    assert "not endorsed or certified by TMDB" in CREDITS_MESSAGE

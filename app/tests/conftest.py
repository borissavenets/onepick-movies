"""Pytest configuration and shared fixtures."""

import os

# Set test environment variables before any imports
# Use valid-format token to pass aiogram validation
os.environ["BOT_TOKEN"] = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
os.environ["BOT_MODE"] = "polling"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_framepick.db"

import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio as the async backend for tests."""
    return "asyncio"

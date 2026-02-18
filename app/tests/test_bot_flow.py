"""Tests for bot UX flow components."""

import os
import pytest

# Set test environment before imports
os.environ["BOT_TOKEN"] = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
os.environ["BOT_MODE"] = "polling"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_framepick.db"

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage.db import Base


@pytest.fixture
async def engine():
    """Create test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///./test_framepick.db",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()

    import os as os_module
    if os_module.path.exists("./test_framepick.db"):
        os_module.remove("./test_framepick.db")


@pytest.fixture
async def session(engine):
    """Create test database session."""
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session


# Test deep-link parsing

def test_parse_deeplink_valid():
    """Test parsing valid deep-link payload."""
    from app.bot.handlers_start import parse_deeplink

    result = parse_deeplink("post_abc123_vvariant1")
    assert result is not None
    assert result["post_id"] == "abc123"
    assert result["variant_id"] == "variant1"


def test_parse_deeplink_with_dashes():
    """Test parsing deep-link with dashes in IDs."""
    from app.bot.handlers_start import parse_deeplink

    result = parse_deeplink("post_my-post-id_vmy-variant")
    assert result is not None
    assert result["post_id"] == "my-post-id"
    assert result["variant_id"] == "my-variant"


def test_parse_deeplink_invalid():
    """Test parsing invalid deep-link payload."""
    from app.bot.handlers_start import parse_deeplink

    assert parse_deeplink(None) is None
    assert parse_deeplink("") is None
    assert parse_deeplink("invalid") is None
    assert parse_deeplink("post_only") is None
    assert parse_deeplink("something_else_entirely") is None


def test_parse_deeplink_completely_invalid():
    """Test that completely invalid formats return None."""
    from app.bot.handlers_start import parse_deeplink

    # No underscore separator
    assert parse_deeplink("postabc123vvariant1") is None
    # Missing post prefix
    assert parse_deeplink("abc123_vvariant1") is None
    # Empty variant
    assert parse_deeplink("post_abc123_v") is None


# Test callback data parsing

def test_parse_callback_simple():
    """Test parsing simple callback data."""
    from app.bot.keyboards import parse_callback

    prefix, value, extra = parse_callback("s:light")
    assert prefix == "s"
    assert value == "light"
    assert extra == []


def test_parse_callback_with_extra():
    """Test parsing callback with extra parameters."""
    from app.bot.keyboards import parse_callback

    prefix, value, extra = parse_callback("p:slow|escape")
    assert prefix == "p"
    assert value == "slow"
    assert extra == ["escape"]


def test_parse_callback_with_multiple_extra():
    """Test parsing callback with multiple extra parameters."""
    from app.bot.keyboards import parse_callback

    prefix, value, extra = parse_callback("f:movie|escape|slow")
    assert prefix == "f"
    assert value == "movie"
    assert extra == ["escape", "slow"]


def test_parse_callback_no_prefix():
    """Test parsing callback without prefix."""
    from app.bot.keyboards import parse_callback

    prefix, value, extra = parse_callback("something")
    assert prefix == ""
    assert value == "something"
    assert extra == []


# Test answer encoding/decoding

def test_encode_decode_answers():
    """Test answer encoding and decoding roundtrip."""
    from app.bot.keyboards import decode_answers, encode_answers

    encoded = encode_answers("escape", "slow", "movie")
    assert encoded == "escape|slow|movie"

    decoded = decode_answers(encoded)
    assert decoded["state"] == "escape"
    assert decoded["pace"] == "slow"
    assert decoded["format"] == "movie"


def test_decode_answers_invalid():
    """Test decoding invalid answers."""
    from app.bot.keyboards import decode_answers

    result = decode_answers("")
    assert result == {}

    result = decode_answers("only|two")
    assert result == {}


# Test session store

def test_session_store_basic():
    """Test basic session store operations."""
    from app.bot.session import SessionStore

    store = SessionStore(ttl_seconds=60)

    # Get or create
    session = store.get_or_create("user1")
    assert session.user_id == "user1"
    assert session.answers == {}

    # Set answers
    store.set_answers("user1", {"state": "light"})
    session = store.get("user1")
    assert session is not None
    assert session.answers["state"] == "light"


def test_session_store_ttl():
    """Test session TTL expiration."""
    import time
    from app.bot.session import SessionStore

    store = SessionStore(ttl_seconds=1)  # 1 second TTL

    store.get_or_create("user1")
    assert store.get("user1") is not None

    # Wait for expiration
    time.sleep(1.5)

    assert store.get("user1") is None


def test_session_store_clear():
    """Test session clearing."""
    from app.bot.session import SessionStore

    store = SessionStore(ttl_seconds=60)

    store.get_or_create("user1")
    assert store.get("user1") is not None

    store.clear("user1")
    assert store.get("user1") is None


def test_session_store_reset_flow():
    """Test flow reset preserves ref info."""
    from app.bot.session import SessionStore

    store = SessionStore(ttl_seconds=60)

    session = store.get_or_create("user1")
    session.answers = {"state": "light", "pace": "slow"}
    session.last_ref = {"post_id": "123"}

    store.reset_flow("user1")

    session = store.get("user1")
    assert session is not None
    assert session.answers == {}
    assert session.last_ref == {"post_id": "123"}


# Test reset clears data

@pytest.mark.anyio
async def test_reset_command_clears_weights(session):
    """Test that /reset clears user weights via UsersRepo."""
    from app.storage import UsersRepo, WeightsRepo

    users_repo = UsersRepo(session)
    weights_repo = WeightsRepo(session)

    # Create user and add weights
    user = await users_repo.get_or_create_user("reset-cmd-user")
    await weights_repo.add_weight_delta(user.user_id, "tone:dark", 5)

    # Verify weight exists
    weight = await weights_repo.get_weight(user.user_id, "tone:dark")
    assert weight == 5

    # Reset user (simulating /reset command)
    await users_repo.reset_user(user.user_id)

    # Verify weight is cleared
    weight_after = await weights_repo.get_weight(user.user_id, "tone:dark")
    assert weight_after == 0


# Test recommendation creates rec row

@pytest.mark.anyio
async def test_recommendation_creates_rec_row(session):
    """Test that get_recommendation creates a recommendation row."""
    from app.core import get_recommendation
    from app.storage import ItemsRepo, RecsRepo, UsersRepo

    # Setup: create user and seed items
    users_repo = UsersRepo(session)
    items_repo = ItemsRepo(session)
    recs_repo = RecsRepo(session)

    user = await users_repo.get_or_create_user("rec-test-user")
    await items_repo.seed_from_json("items_seed/curated_items.json")

    # Get recommendation
    answers = {"state": "escape", "pace": "slow", "format": "movie"}
    result = await get_recommendation(
        session=session,
        user_id=user.user_id,
        answers=answers,
        mode="normal",
    )

    assert result is not None
    assert result.rec_id is not None
    assert result.item_id is not None
    assert result.title is not None

    # Verify rec row was created
    rec = await recs_repo.get_rec(result.rec_id)
    assert rec is not None
    assert rec.user_id == user.user_id
    assert rec.item_id == result.item_id


# Test keyboard builders

def test_kb_start():
    """Test start keyboard has correct structure."""
    from app.bot.keyboards import kb_start

    kb = kb_start()
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].text == "Pick now"
    assert kb.inline_keyboard[0][0].callback_data == "n:pick"


def test_kb_state():
    """Test state keyboard has correct options."""
    from app.bot.keyboards import kb_state

    kb = kb_state()
    assert len(kb.inline_keyboard) == 2

    # First row: Light, Heavy
    assert kb.inline_keyboard[0][0].callback_data == "s:light"
    assert kb.inline_keyboard[0][1].callback_data == "s:heavy"

    # Second row: Escape
    assert kb.inline_keyboard[1][0].callback_data == "s:escape"


def test_kb_pace_encodes_state():
    """Test pace keyboard encodes state in callback."""
    from app.bot.keyboards import kb_pace

    kb = kb_pace("escape")
    assert "escape" in kb.inline_keyboard[0][0].callback_data
    assert "escape" in kb.inline_keyboard[0][1].callback_data


def test_kb_format_encodes_state_and_pace():
    """Test format keyboard encodes state and pace."""
    from app.bot.keyboards import kb_format

    kb = kb_format("escape", "slow")
    callback = kb.inline_keyboard[0][0].callback_data
    assert "escape" in callback
    assert "slow" in callback


def test_kb_recommendation():
    """Test recommendation keyboard has all actions."""
    from app.bot.keyboards import kb_recommendation

    kb = kb_recommendation("abc12345-6789")

    # Flatten all callbacks
    callbacks = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
    ]

    # Check all actions present
    callbacks_non_null = [c for c in callbacks if c]
    assert any("a:hit" in c for c in callbacks_non_null)
    assert any("a:another" in c for c in callbacks_non_null)
    assert any("n:pick" in c for c in callbacks_non_null)
    assert any("a:fav" in c for c in callbacks_non_null)
    assert any("a:seen" in c for c in callbacks_non_null)

    # Check rec_id is truncated
    assert any("abc12345" in c for c in callbacks)

"""Tests for storage layer."""

import os
import pytest
from datetime import datetime, timezone

# Set test environment before imports (use valid-format token)
os.environ["BOT_TOKEN"] = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
os.environ["BOT_MODE"] = "polling"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_framepick.db"

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage import (
    Base,
    ItemsRepo,
    UsersRepo,
    WeightsRepo,
    FavoritesRepo,
    RecsRepo,
    FeedbackRepo,
    EventsRepo,
)


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

    # Cleanup test database file
    import os
    if os.path.exists("./test_framepick.db"):
        os.remove("./test_framepick.db")


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


@pytest.mark.anyio
async def test_user_create_and_get(session):
    """Test user creation and retrieval."""
    users_repo = UsersRepo(session)

    user = await users_repo.get_or_create_user("12345")
    assert user.user_id == "12345"
    assert user.created_at is not None
    assert user.last_seen_at is not None

    # Getting same user should return existing
    user2 = await users_repo.get_or_create_user("12345")
    assert user2.user_id == user.user_id
    assert user2.created_at == user.created_at


@pytest.mark.anyio
async def test_user_reset_clears_weights(session):
    """Test that resetting a user clears their weights."""
    users_repo = UsersRepo(session)
    weights_repo = WeightsRepo(session)

    # Create user and add weights
    user = await users_repo.get_or_create_user("reset-test-user")

    await weights_repo.add_weight_delta(user.user_id, "tone:dark", 5)
    await weights_repo.add_weight_delta(user.user_id, "pace:fast", 3)

    # Verify weights exist
    weight1 = await weights_repo.get_weight(user.user_id, "tone:dark")
    assert weight1 == 5

    weight2 = await weights_repo.get_weight(user.user_id, "pace:fast")
    assert weight2 == 3

    # Reset user
    await users_repo.reset_user(user.user_id)

    # Verify weights are cleared
    weight1_after = await weights_repo.get_weight(user.user_id, "tone:dark")
    assert weight1_after == 0

    weight2_after = await weights_repo.get_weight(user.user_id, "pace:fast")
    assert weight2_after == 0

    # Verify user still exists with reset_at set
    user_after = await users_repo.get_user(user.user_id)
    assert user_after is not None
    assert user_after.reset_at is not None


@pytest.mark.anyio
async def test_seed_items_idempotent(session):
    """Test that seeding items is idempotent."""
    items_repo = ItemsRepo(session)

    # First seed
    count1 = await items_repo.seed_from_json("items_seed/curated_items.json")
    assert count1 == 5

    # Get count after first seed
    total1 = await items_repo.count_items()
    assert total1 == 5

    # Second seed (should not duplicate)
    count2 = await items_repo.seed_from_json("items_seed/curated_items.json")
    assert count2 == 5

    # Get count after second seed (should be same)
    total2 = await items_repo.count_items()
    assert total2 == 5

    # Verify item data
    item = await items_repo.get_item("cur-0001")
    assert item is not None
    assert item.title == "The Shawshank Redemption"
    assert item.type == "movie"


@pytest.mark.anyio
async def test_weights_bulk_add(session):
    """Test bulk weight delta operations."""
    users_repo = UsersRepo(session)
    weights_repo = WeightsRepo(session)

    user = await users_repo.get_or_create_user("bulk-test-user")

    # Add bulk deltas
    await weights_repo.bulk_add_weight_deltas(
        user.user_id,
        {
            "tone:warm": 2,
            "tone:dark": -1,
            "pace:slow": 3,
        },
    )

    # Verify
    assert await weights_repo.get_weight(user.user_id, "tone:warm") == 2
    assert await weights_repo.get_weight(user.user_id, "tone:dark") == -1
    assert await weights_repo.get_weight(user.user_id, "pace:slow") == 3

    # Add more to existing
    await weights_repo.bulk_add_weight_deltas(
        user.user_id,
        {
            "tone:warm": 1,
            "pace:slow": -1,
        },
    )

    assert await weights_repo.get_weight(user.user_id, "tone:warm") == 3
    assert await weights_repo.get_weight(user.user_id, "pace:slow") == 2


@pytest.mark.anyio
async def test_favorites_operations(session):
    """Test favorites add/remove/check."""
    users_repo = UsersRepo(session)
    items_repo = ItemsRepo(session)
    favorites_repo = FavoritesRepo(session)

    user = await users_repo.get_or_create_user("fav-test-user")

    # Seed items first
    await items_repo.seed_from_json("items_seed/curated_items.json")

    # Add favorite
    added = await favorites_repo.add_favorite(user.user_id, "cur-0001")
    assert added is True

    # Check if favorited
    is_fav = await favorites_repo.is_favorited(user.user_id, "cur-0001")
    assert is_fav is True

    # Adding same favorite again should return False
    added_again = await favorites_repo.add_favorite(user.user_id, "cur-0001")
    assert added_again is False

    # Remove favorite
    removed = await favorites_repo.remove_favorite(user.user_id, "cur-0001")
    assert removed is True

    # Check if still favorited
    is_fav_after = await favorites_repo.is_favorited(user.user_id, "cur-0001")
    assert is_fav_after is False


@pytest.mark.anyio
async def test_recommendations_and_feedback(session):
    """Test recommendation creation and feedback."""
    users_repo = UsersRepo(session)
    items_repo = ItemsRepo(session)
    recs_repo = RecsRepo(session)
    feedback_repo = FeedbackRepo(session)

    user = await users_repo.get_or_create_user("rec-test-user")
    await items_repo.seed_from_json("items_seed/curated_items.json")

    # Create recommendation
    rec_id = await recs_repo.create_rec(
        user_id=user.user_id,
        item_id="cur-0001",
        context={"state": "escape", "pace": "slow"},
    )
    assert rec_id is not None

    # Get recommendation
    rec = await recs_repo.get_rec(rec_id)
    assert rec is not None
    assert rec.item_id == "cur-0001"
    assert rec.item is not None
    assert rec.item.title == "The Shawshank Redemption"

    # Add feedback
    feedback = await feedback_repo.add_feedback(
        user_id=user.user_id,
        rec_id=rec_id,
        action="hit",
        reason="Great suggestion!",
    )
    assert feedback.action == "hit"

    # Count feedback
    count = await feedback_repo.count_feedback(rec_id)
    assert count == 1


@pytest.mark.anyio
async def test_events_logging(session):
    """Test event logging and retrieval."""
    events_repo = EventsRepo(session)

    # Log events
    event1 = await events_repo.log_event(
        event_name="bot_start",
        user_id="event-test-user",
        payload={"source": "deeplink"},
    )
    assert event1.event_name == "bot_start"

    event2 = await events_repo.log_event(
        event_name="rec_shown",
        user_id="event-test-user",
        rec_id="some-rec-id",
        payload={"item_id": "cur-0001"},
    )

    # List events
    events = await events_repo.list_events(user_id="event-test-user")
    assert len(events) == 2

    # List by event name
    start_events = await events_repo.list_events(event_name="bot_start")
    assert len(start_events) == 1
    assert start_events[0].user_id == "event-test-user"


@pytest.mark.anyio
async def test_items_list_candidates(session):
    """Test item candidate listing with filters."""
    items_repo = ItemsRepo(session)

    # Seed items
    await items_repo.seed_from_json("items_seed/curated_items.json")

    # List all
    all_items = await items_repo.list_candidates()
    assert len(all_items) == 5

    # Filter by type
    movies = await items_repo.list_candidates(item_type="movie")
    assert len(movies) == 3

    series = await items_repo.list_candidates(item_type="series")
    assert len(series) == 2

    # Exclude IDs
    filtered = await items_repo.list_candidates(exclude_ids={"cur-0001", "cur-0002"})
    assert len(filtered) == 3

    # Filter by tags (in-memory)
    cozy = await items_repo.list_candidates(filter_tags={"tone": ["cozy"]})
    assert len(cozy) == 2  # Amélie and Ted Lasso

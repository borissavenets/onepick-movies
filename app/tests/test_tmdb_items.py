"""Tests for TMDB item functionality."""

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
    """Create test database engine with new schema."""
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


# Test heuristic_tags function

def test_heuristic_tags_action_movie():
    """Test heuristic tags for action movie."""
    import json
    from app.storage.heuristics import heuristic_tags

    tags_json = heuristic_tags(
        genres=["Action", "Thriller"],
        overview="An explosive chase through the city.",
        vote_average=7.5,
    )

    tags = json.loads(tags_json)
    assert tags["pace"] == ["fast"]
    assert tags["intensity"] >= 3


def test_heuristic_tags_drama():
    """Test heuristic tags for drama."""
    import json
    from app.storage.heuristics import heuristic_tags

    tags_json = heuristic_tags(
        genres=["Drama"],
        overview="A touching story of loss and redemption.",
        vote_average=8.0,
    )

    tags = json.loads(tags_json)
    assert tags["pace"] == ["slow"]
    assert "heavy" in tags["mood"] or tags["mood"] == ["heavy"]


def test_heuristic_tags_comedy():
    """Test heuristic tags for comedy."""
    import json
    from app.storage.heuristics import heuristic_tags

    tags_json = heuristic_tags(
        genres=["Comedy", "Romance"],
        overview="A hilarious romantic comedy.",
    )

    tags = json.loads(tags_json)
    assert "light" in tags["mood"]
    assert "funny" in tags["tone"]


def test_heuristic_tags_with_tmdb_genre_ids():
    """Test heuristic tags with TMDB genre IDs."""
    import json
    from app.storage.heuristics import heuristic_tags

    # TMDB genre IDs: 28=Action, 878=SciFi
    tags_json = heuristic_tags(
        genres=[28, 878],
        overview="A futuristic action adventure.",
    )

    tags = json.loads(tags_json)
    assert tags["pace"] == ["fast"]
    assert "weird" in tags["tone"] or "escape" in tags["mood"]


def test_heuristic_tags_empty_genres():
    """Test heuristic tags with empty genres."""
    import json
    from app.storage.heuristics import heuristic_tags

    tags_json = heuristic_tags(genres=[], overview=None)

    tags = json.loads(tags_json)
    assert "pace" in tags
    assert "mood" in tags
    assert "tone" in tags
    assert "intensity" in tags


# Test upsert_tmdb_item

@pytest.mark.anyio
async def test_upsert_tmdb_item_creates_new(session):
    """Test that upsert_tmdb_item creates a new item."""
    from app.storage import ItemsRepo

    items_repo = ItemsRepo(session)

    item = await items_repo.upsert_tmdb_item(
        tmdb_id=550,
        item_type="movie",
        title="Fight Club",
        overview="An insomniac office worker and a devil-may-care soap maker...",
        genres=["Drama", "Thriller"],
        language="en",
        popularity=50.0,
        vote_average=8.4,
        vote_count=25000,
    )

    assert item is not None
    assert item.source == "tmdb"
    assert item.source_id == "550"
    assert item.title == "Fight Club"
    assert item.tag_status == "pending"
    assert item.item_id == "tmdb-550"


@pytest.mark.anyio
async def test_upsert_tmdb_item_idempotent(session):
    """Test that upsert_tmdb_item is idempotent."""
    from app.storage import ItemsRepo

    items_repo = ItemsRepo(session)

    # First upsert
    item1 = await items_repo.upsert_tmdb_item(
        tmdb_id=550,
        item_type="movie",
        title="Fight Club",
        genres=["Drama"],
        popularity=50.0,
    )

    count1 = await items_repo.count_items(source="tmdb")
    assert count1 == 1

    # Second upsert with updated title
    item2 = await items_repo.upsert_tmdb_item(
        tmdb_id=550,
        item_type="movie",
        title="Fight Club (Updated)",
        genres=["Drama", "Thriller"],
        popularity=60.0,
    )

    count2 = await items_repo.count_items(source="tmdb")
    assert count2 == 1  # Still only 1 item

    # Verify title was updated
    item = await items_repo.get_item_by_source("tmdb", "550")
    assert item is not None
    assert item.title == "Fight Club (Updated)"


@pytest.mark.anyio
async def test_upsert_multiple_tmdb_items(session):
    """Test upserting multiple different TMDB items."""
    from app.storage import ItemsRepo

    items_repo = ItemsRepo(session)

    await items_repo.upsert_tmdb_item(
        tmdb_id=550,
        item_type="movie",
        title="Fight Club",
        genres=["Drama"],
    )

    await items_repo.upsert_tmdb_item(
        tmdb_id=680,
        item_type="movie",
        title="Pulp Fiction",
        genres=["Crime", "Drama"],
    )

    await items_repo.upsert_tmdb_item(
        tmdb_id=1399,
        item_type="series",
        title="Game of Thrones",
        genres=["Drama", "Fantasy"],
    )

    count = await items_repo.count_items(source="tmdb")
    assert count == 3


# Test seed_from_json with new fields

@pytest.mark.anyio
async def test_seed_from_json_sets_curated_fields(session):
    """Test that seed_from_json sets correct source fields."""
    from app.storage import ItemsRepo

    items_repo = ItemsRepo(session)

    count = await items_repo.seed_from_json("items_seed/curated_items.json")
    assert count == 5

    # Check one item has correct fields
    item = await items_repo.get_item("cur-0001")
    assert item is not None
    assert item.source == "curated"
    assert item.source_id is None
    assert item.tag_status == "tagged"
    assert item.updated_at is not None


@pytest.mark.anyio
async def test_seed_from_json_still_idempotent(session):
    """Test that seed_from_json is still idempotent with new fields."""
    from app.storage import ItemsRepo

    items_repo = ItemsRepo(session)

    # First seed
    await items_repo.seed_from_json("items_seed/curated_items.json")
    count1 = await items_repo.count_items()

    # Second seed
    await items_repo.seed_from_json("items_seed/curated_items.json")
    count2 = await items_repo.count_items()

    assert count1 == count2 == 5


# Test list_candidates with source_preference

@pytest.mark.anyio
async def test_list_candidates_source_preference(session):
    """Test list_candidates with source_preference filter."""
    from app.storage import ItemsRepo

    items_repo = ItemsRepo(session)

    # Seed curated items
    await items_repo.seed_from_json("items_seed/curated_items.json")

    # Add TMDB items
    await items_repo.upsert_tmdb_item(
        tmdb_id=550,
        item_type="movie",
        title="Fight Club",
        genres=["Drama"],
    )

    # List only curated
    curated = await items_repo.list_candidates(source_preference="curated")
    assert all(i.source == "curated" for i in curated)
    assert len(curated) == 5

    # List only tmdb
    tmdb = await items_repo.list_candidates(source_preference="tmdb")
    assert all(i.source == "tmdb" for i in tmdb)
    assert len(tmdb) == 1

    # List any
    all_items = await items_repo.list_candidates(source_preference="any")
    assert len(all_items) == 6


# Test update_tags

@pytest.mark.anyio
async def test_update_tags(session):
    """Test updating item tags."""
    import json
    from app.storage import ItemsRepo

    items_repo = ItemsRepo(session)

    # Create item
    await items_repo.upsert_tmdb_item(
        tmdb_id=550,
        item_type="movie",
        title="Fight Club",
        genres=["Drama"],
    )

    item = await items_repo.get_item("tmdb-550")
    assert item is not None
    assert item.tag_status == "pending"
    assert item.tag_version == 1

    # Update tags
    new_tags = json.dumps({
        "pace": ["fast"],
        "mood": ["heavy"],
        "tone": ["dark", "tense"],
        "intensity": 4,
    })

    updated = await items_repo.update_tags(
        item_id="tmdb-550",
        tags_json=new_tags,
        tag_status="tagged",
    )

    assert updated is True

    # Verify
    item = await items_repo.get_item("tmdb-550")
    assert item is not None
    assert item.tag_status == "tagged"
    assert item.tag_version == 2
    tags = json.loads(item.tags_json)
    assert tags["intensity"] == 4

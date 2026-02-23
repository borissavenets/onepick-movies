"""Tests for TMDB sync functionality."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment before imports
os.environ["BOT_TOKEN"] = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
os.environ["BOT_MODE"] = "polling"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_onepick.db"
os.environ["TMDB_BEARER_TOKEN"] = "test_token"
os.environ["TMDB_SYNC_ENABLED"] = "true"
os.environ["TMDB_PAGES_PER_RUN"] = "1"
os.environ["TMDB_MAX_ITEMS_PER_RUN"] = "10"

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage.db import Base


@pytest.fixture
async def engine():
    """Create test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///./test_onepick.db",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()

    import os as os_module
    if os_module.path.exists("./test_onepick.db"):
        os_module.remove("./test_onepick.db")


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


# Test base_score formula monotonicity

def test_base_score_formula_monotonicity():
    """Test that base_score increases with better metrics."""
    from app.jobs.tmdb_sync import calculate_base_score

    # Higher vote_average should give higher score
    score_low = calculate_base_score(vote_average=5.0, vote_count=100, popularity=10.0)
    score_high = calculate_base_score(vote_average=9.0, vote_count=100, popularity=10.0)
    assert score_high > score_low

    # Higher vote_count should give higher score
    score_low = calculate_base_score(vote_average=7.0, vote_count=100, popularity=10.0)
    score_high = calculate_base_score(vote_average=7.0, vote_count=10000, popularity=10.0)
    assert score_high > score_low

    # Higher popularity should give higher score
    score_low = calculate_base_score(vote_average=7.0, vote_count=100, popularity=10.0)
    score_high = calculate_base_score(vote_average=7.0, vote_count=100, popularity=500.0)
    assert score_high > score_low


def test_base_score_formula_handles_none():
    """Test that base_score handles None values."""
    from app.jobs.tmdb_sync import calculate_base_score

    score = calculate_base_score(vote_average=None, vote_count=None, popularity=None)
    assert score == 0.0

    score = calculate_base_score(vote_average=8.0, vote_count=None, popularity=None)
    assert score == 4.0  # 0.5 * 8.0


# Test item data extraction

def test_extract_item_data_movie():
    """Test extracting data from a movie item."""
    from app.jobs.tmdb_sync import extract_item_data

    item = {
        "id": 550,
        "title": "Fight Club",
        "original_title": "Fight Club",
        "overview": "A ticking-Loss-bomb of a movie...",
        "release_date": "1999-10-15",
        "original_language": "en",
        "genre_ids": [18, 53],
        "popularity": 50.5,
        "vote_average": 8.4,
        "vote_count": 25000,
    }

    data = extract_item_data(item, "movie")
    assert data is not None
    assert data["tmdb_id"] == 550
    assert data["title"] == "Fight Club"
    assert data["item_type"] == "movie"
    assert data["genre_ids"] == [18, 53]


def test_extract_item_data_tv():
    """Test extracting data from a TV item."""
    from app.jobs.tmdb_sync import extract_item_data

    item = {
        "id": 1399,
        "name": "Game of Thrones",
        "original_name": "Game of Thrones",
        "overview": "Seven noble families fight...",
        "first_air_date": "2011-04-17",
        "original_language": "en",
        "genre_ids": [18, 10765],
        "popularity": 100.0,
        "vote_average": 8.4,
        "vote_count": 15000,
    }

    data = extract_item_data(item, "tv")
    assert data is not None
    assert data["tmdb_id"] == 1399
    assert data["title"] == "Game of Thrones"
    assert data["item_type"] == "series"


def test_extract_item_data_missing_id():
    """Test that items without ID return None."""
    from app.jobs.tmdb_sync import extract_item_data

    item = {"title": "No ID Movie"}
    data = extract_item_data(item, "movie")
    assert data is None


def test_extract_item_data_missing_title():
    """Test that items without title return None."""
    from app.jobs.tmdb_sync import extract_item_data

    item = {"id": 123}
    data = extract_item_data(item, "movie")
    assert data is None


# Test TMDB client retry logic

@pytest.mark.anyio
async def test_tmdb_client_retries_on_429():
    """Test that TMDB client retries on 429 rate limit."""
    from app.providers.tmdb_client import TMDBClient, TMDBRateLimitError

    client = TMDBClient(bearer_token="test_token")

    # Mock the httpx client
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    mock_response_429.headers = {"Retry-After": "1"}

    mock_response_ok = MagicMock()
    mock_response_ok.status_code = 200
    mock_response_ok.json.return_value = {"results": []}

    call_count = 0

    async def mock_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return mock_response_429
        return mock_response_ok

    with patch.object(client, "_get_client") as mock_get_client:
        mock_http_client = AsyncMock()
        mock_http_client.request = mock_request
        mock_get_client.return_value = mock_http_client

        # Should retry and eventually succeed
        result = await client._request("GET", "/test")
        assert result == {"results": []}
        assert call_count == 3  # 2 retries + 1 success

    await client.close()


@pytest.mark.anyio
async def test_tmdb_client_raises_after_max_retries():
    """Test that TMDB client raises after max retries on 429."""
    from app.providers.tmdb_client import TMDBClient, TMDBRateLimitError, MAX_RETRIES

    client = TMDBClient(bearer_token="test_token")

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "0"}  # 0 second wait for test speed

    async def mock_request(*args, **kwargs):
        return mock_response

    with patch.object(client, "_get_client") as mock_get_client:
        mock_http_client = AsyncMock()
        mock_http_client.request = mock_request
        mock_get_client.return_value = mock_http_client

        with pytest.raises(TMDBRateLimitError):
            await client._request("GET", "/test")

    await client.close()


# Test sync idempotency

@pytest.mark.anyio
async def test_tmdb_sync_upserts_idempotently(session):
    """Test that running sync twice doesn't create duplicates."""
    from app.storage import ItemsRepo

    items_repo = ItemsRepo(session)

    # First upsert
    await items_repo.upsert_tmdb_item(
        tmdb_id=550,
        item_type="movie",
        title="Fight Club",
        overview="A movie about...",
        genres=[18, 53],
        popularity=50.0,
        vote_average=8.4,
        vote_count=25000,
    )

    count1 = await items_repo.count_items(source="tmdb")
    assert count1 == 1

    # Second upsert (simulating second sync run)
    await items_repo.upsert_tmdb_item(
        tmdb_id=550,
        item_type="movie",
        title="Fight Club",
        overview="A movie about...",
        genres=[18, 53],
        popularity=55.0,  # Updated popularity
        vote_average=8.5,  # Updated rating
        vote_count=26000,
    )

    count2 = await items_repo.count_items(source="tmdb")
    assert count2 == 1  # Still only 1 item

    # Third upsert of different item
    await items_repo.upsert_tmdb_item(
        tmdb_id=680,
        item_type="movie",
        title="Pulp Fiction",
        genres=[18, 80],
        popularity=60.0,
    )

    count3 = await items_repo.count_items(source="tmdb")
    assert count3 == 2  # Now 2 items


# Test sync with mocked TMDB client

@pytest.mark.anyio
async def test_sync_job_processes_items(session):
    """Test that sync job processes and upserts items."""
    from app.jobs.tmdb_sync import extract_item_data, calculate_base_score
    from app.storage import ItemsRepo

    # Create mock TMDB response
    mock_movie = {
        "id": 550,
        "title": "Fight Club",
        "overview": "An insomniac office worker...",
        "release_date": "1999-10-15",
        "original_language": "en",
        "genre_ids": [18, 53],
        "popularity": 50.5,
        "vote_average": 8.4,
        "vote_count": 25000,
    }

    # Extract and verify
    data = extract_item_data(mock_movie, "movie")
    assert data is not None

    # Calculate score
    score = calculate_base_score(
        vote_average=data["vote_average"],
        vote_count=data["vote_count"],
        popularity=data["popularity"],
    )
    assert score > 0

    # Upsert
    items_repo = ItemsRepo(session)
    item = await items_repo.upsert_tmdb_item(
        tmdb_id=data["tmdb_id"],
        item_type=data["item_type"],
        title=data["title"],
        overview=data["overview"],
        genres=data["genre_ids"],
        language=data["language"],
        popularity=data["popularity"],
        vote_average=data["vote_average"],
        vote_count=data["vote_count"],
    )

    assert item is not None
    assert item.source == "tmdb"
    assert item.source_id == "550"
    assert item.title == "Fight Club"
    assert item.tag_status == "pending"

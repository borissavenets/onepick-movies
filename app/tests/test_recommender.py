"""Tests for the recommendation engine."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment before imports
os.environ["BOT_TOKEN"] = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
os.environ["BOT_MODE"] = "polling"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_onepick.db"
os.environ["RECS_EPSILON"] = "0.30"
os.environ["RECS_ANTI_REPEAT_DAYS"] = "90"

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.storage.db import Base
from app.storage import ItemsRepo, RecsRepo, FavoritesRepo, WeightsRepo, UsersRepo


@pytest.fixture
async def engine():
    """Create test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///./test_recommender.db",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()

    import os as os_module
    if os_module.path.exists("./test_recommender.db"):
        os_module.remove("./test_recommender.db")


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


# Test tagging module

def test_parse_tags_valid():
    """Test parsing valid tags JSON."""
    from app.core.tagging import parse_tags

    tags = parse_tags('{"pace": "slow", "mood": ["light"]}')
    assert tags is not None
    assert tags["pace"] == "slow"
    assert tags["mood"] == ["light"]


def test_parse_tags_invalid():
    """Test parsing invalid tags JSON."""
    from app.core.tagging import parse_tags

    assert parse_tags(None) is None
    assert parse_tags("") is None
    assert parse_tags("invalid json") is None
    assert parse_tags("[]") is None  # Not a dict


def test_normalize_pace():
    """Test pace normalization."""
    from app.core.tagging import normalize_pace

    assert normalize_pace("slow") == "slow"
    assert normalize_pace("fast") == "fast"
    assert normalize_pace("meditative") == "slow"
    assert normalize_pace("dynamic") == "fast"
    assert normalize_pace("medium") == "slow"  # Defaults to slow
    assert normalize_pace(None) is None


def test_normalize_mood():
    """Test mood normalization."""
    from app.core.tagging import normalize_mood

    assert "light" in normalize_mood("light")
    assert "light" in normalize_mood("uplifting")
    assert "heavy" in normalize_mood("dark")
    assert "escape" in normalize_mood("adventure")
    # Order is not guaranteed due to set()
    result = normalize_mood(["light", "heavy"])
    assert set(result) == {"light", "heavy"}
    assert normalize_mood(None) == []


def test_match_score_pace_match():
    """Test match score with pace matching."""
    from app.core.tagging import match_score

    tags = {"pace": "slow", "mood": ["light"]}
    answers = {"state": "light", "pace": "slow", "format": "movie"}

    score = match_score(tags, answers)
    assert score >= 2.0  # Pace match


def test_match_score_mood_match():
    """Test match score with mood matching."""
    from app.core.tagging import match_score

    tags = {"pace": "fast", "mood": ["light"]}
    answers = {"state": "light", "pace": "fast", "format": "movie"}

    score = match_score(tags, answers)
    assert score >= 4.0  # Pace + mood match


def test_match_score_no_tags():
    """Test match score without tags."""
    from app.core.tagging import match_score

    # Without require_tags
    score = match_score(None, {"state": "light", "pace": "slow", "format": "movie"})
    assert score == 0.0

    # With require_tags
    score = match_score(None, {"state": "light"}, require_tags=True)
    assert score == float("-inf")


def test_context_key():
    """Test context key generation."""
    from app.core.tagging import context_key

    key = context_key({"state": "light", "pace": "slow", "format": "movie"})
    assert key == "state:light|pace:slow|format:movie"


# Test rationale module

def test_rationale_length():
    """Test that rationale is within length limit."""
    from app.core.rationale import generate_rationale, MAX_RATIONALE_LENGTH

    answers = {"state": "escape", "pace": "fast", "format": "movie"}
    rationale = generate_rationale("test-rec-id", answers)

    assert len(rationale) <= MAX_RATIONALE_LENGTH


def test_rationale_no_spoilers():
    """Test that rationale doesn't contain spoiler keywords."""
    from app.core.rationale import generate_rationale, SPOILER_KEYWORDS

    answers = {"state": "heavy", "pace": "slow", "format": "movie"}

    # Generate multiple rationales to increase coverage
    for i in range(20):
        rationale = generate_rationale(f"test-rec-{i}", answers)
        rationale_lower = rationale.lower()
        for keyword in SPOILER_KEYWORDS:
            assert keyword not in rationale_lower, f"Found spoiler '{keyword}' in rationale"


def test_rationale_deterministic():
    """Test that rationale is deterministic for same rec_id."""
    from app.core.rationale import generate_rationale

    answers = {"state": "light", "pace": "slow", "format": "movie"}

    r1 = generate_rationale("same-rec-id", answers)
    r2 = generate_rationale("same-rec-id", answers)
    assert r1 == r2


def test_when_to_watch():
    """Test when-to-watch generation."""
    from app.core.rationale import generate_when_to_watch

    answers = {"state": "light", "pace": "slow", "format": "movie"}
    when = generate_when_to_watch("test-rec", answers)

    assert len(when) > 0
    assert len(when) < 200  # Reasonable length


def test_delta_explainer():
    """Test delta explainer generation."""
    from app.core.rationale import generate_delta_explainer

    explainer = generate_delta_explainer("pace_flipped", "fast", "test-rec")
    assert "fast" in explainer.lower()


# Test anti-repeat module

@pytest.mark.anyio
async def test_anti_repeat_excludes_recent(session):
    """Test that anti-repeat excludes recently recommended items."""
    from app.core.anti_repeat import get_excluded_item_ids

    # Create user
    users_repo = UsersRepo(session)
    await users_repo.get_or_create_user("test-user-1")

    # Create items
    items_repo = ItemsRepo(session)
    item1 = await items_repo.create_item(
        item_id="item-1",
        title="Test Movie 1",
        item_type="movie",
        tags={"pace": "slow"},
    )
    item2 = await items_repo.create_item(
        item_id="item-2",
        title="Test Movie 2",
        item_type="movie",
        tags={"pace": "fast"},
    )

    # Create recommendation for item1
    recs_repo = RecsRepo(session)
    await recs_repo.create_rec(
        user_id="test-user-1",
        item_id="item-1",
        context={"state": "light", "pace": "slow", "format": "movie"},
    )

    # Check exclusions
    excluded = await get_excluded_item_ids(session, "test-user-1")
    assert "item-1" in excluded
    assert "item-2" not in excluded


@pytest.mark.anyio
async def test_anti_repeat_allows_favorited(session):
    """Test that favorited items bypass anti-repeat."""
    from app.core.anti_repeat import get_excluded_item_ids

    # Create user
    users_repo = UsersRepo(session)
    await users_repo.get_or_create_user("test-user-2")

    # Create item
    items_repo = ItemsRepo(session)
    await items_repo.create_item(
        item_id="fav-item",
        title="Favorite Movie",
        item_type="movie",
        tags={"pace": "slow"},
    )

    # Create recommendation
    recs_repo = RecsRepo(session)
    await recs_repo.create_rec(
        user_id="test-user-2",
        item_id="fav-item",
        context={"state": "light", "pace": "slow", "format": "movie"},
    )

    # Add to favorites
    favorites_repo = FavoritesRepo(session)
    await favorites_repo.add_favorite("test-user-2", "fav-item")

    # Check exclusions - favorited item should NOT be excluded
    excluded = await get_excluded_item_ids(session, "test-user-2")
    assert "fav-item" not in excluded


# Test learning module

@pytest.mark.anyio
async def test_update_weights_hit(session):
    """Test weight update for hit action."""
    from app.core.learning import update_weights

    # Create user
    users_repo = UsersRepo(session)
    await users_repo.get_or_create_user("test-user-3")

    # Create item
    items_repo = ItemsRepo(session)
    await items_repo.create_item(
        item_id="weight-item",
        title="Weight Test Movie",
        item_type="movie",
        tags={"pace": "slow"},
    )

    # Create recommendation
    recs_repo = RecsRepo(session)
    rec_id = await recs_repo.create_rec(
        user_id="test-user-3",
        item_id="weight-item",
        context={"state": "light", "pace": "slow", "format": "movie"},
    )

    # Update weights
    changes = await update_weights(session, "test-user-3", rec_id, "hit")

    # Check weight was updated
    assert len(changes) > 0
    key = "state:light|pace:slow|format:movie"
    assert key in changes
    assert changes[key] == 2  # Hit reward


@pytest.mark.anyio
async def test_update_weights_miss_with_reason(session):
    """Test weight update for miss with reason."""
    from app.core.learning import update_weights

    # Create user
    users_repo = UsersRepo(session)
    await users_repo.get_or_create_user("test-user-4")

    # Create item
    items_repo = ItemsRepo(session)
    await items_repo.create_item(
        item_id="miss-item",
        title="Miss Test Movie",
        item_type="movie",
        tags={"pace": "slow"},
    )

    # Create recommendation
    recs_repo = RecsRepo(session)
    rec_id = await recs_repo.create_rec(
        user_id="test-user-4",
        item_id="miss-item",
        context={"state": "heavy", "pace": "slow", "format": "movie"},
    )

    # Update weights with "tooslow" reason
    changes = await update_weights(session, "test-user-4", rec_id, "miss", reason="tooslow")

    # Check weights were updated
    # Should have negative for current context, positive for opposite pace
    assert len(changes) >= 1


# Test epsilon-greedy selection

def test_epsilon_zero_picks_best():
    """Test that epsilon=0 always picks best score."""
    from app.core.recommender import epsilon_greedy_select_deterministic, ScoredCandidate
    from app.storage.models import Item
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    # Create mock items
    items = [
        Item(item_id=f"item-{i}", title=f"Movie {i}", type="movie",
             tags_json="{}", base_score=float(i), curated=True,
             created_at=now, source="curated", tag_status="tagged",
             tag_version=1, updated_at=now)
        for i in range(10)
    ]

    # Create scored candidates with increasing scores
    scored = [
        ScoredCandidate(
            item=items[i],
            score=float(i),
            tags={},
            match_score=0.0,
            weight_bonus=0.0,
            novelty_bonus=0.0,
        )
        for i in range(10)
    ]
    scored.sort(key=lambda x: x.score, reverse=True)

    # With epsilon=0, should always pick the best
    for seed in range(10):
        selected = epsilon_greedy_select_deterministic(scored, epsilon=0.0, seed=seed)
        assert selected.item.item_id == "item-9"  # Highest score


def test_epsilon_one_explores():
    """Test that epsilon=1 explores randomly."""
    from app.core.recommender import epsilon_greedy_select_deterministic, ScoredCandidate
    from app.storage.models import Item
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    items = [
        Item(item_id=f"item-{i}", title=f"Movie {i}", type="movie",
             tags_json="{}", base_score=float(i), curated=True,
             created_at=now, source="curated", tag_status="tagged",
             tag_version=1, updated_at=now)
        for i in range(20)
    ]

    scored = [
        ScoredCandidate(
            item=items[i],
            score=float(i),
            tags={},
            match_score=0.0,
            weight_bonus=0.0,
            novelty_bonus=0.0,
        )
        for i in range(20)
    ]
    scored.sort(key=lambda x: x.score, reverse=True)

    # With epsilon=1, should explore (not always pick best)
    selections = set()
    for seed in range(100):
        selected = epsilon_greedy_select_deterministic(scored, epsilon=1.0, seed=seed)
        selections.add(selected.item.item_id)

    # Should have selected multiple different items
    assert len(selections) > 1


# Test another-but-different logic

def test_another_flips_pace():
    """Test that 'another' mode flips pace when appropriate."""
    from app.core.recommender import _apply_another_delta

    answers = {"state": "light", "pace": "slow", "format": "movie"}
    last_context = {"state": "light", "pace": "slow", "format": "movie"}

    delta_info, new_answers, explainer = _apply_another_delta(answers, last_context, None)

    assert delta_info.get("pace_flipped") is True
    assert new_answers["pace"] == "fast"  # Flipped from slow
    assert explainer is not None


def test_another_tone_shift_when_pace_already_flipped():
    """Test that 'another' shifts tone when pace was already flipped."""
    from app.core.recommender import _apply_another_delta

    answers = {"state": "light", "pace": "fast", "format": "movie"}
    last_context = {
        "state": "light",
        "pace": "fast",
        "format": "movie",
        "delta": {"pace_flipped": True},  # Pace was already flipped
    }

    delta_info, new_answers, explainer = _apply_another_delta(answers, last_context, None)

    # Should shift tone instead
    assert delta_info.get("tone_shifted") is True
    assert explainer is not None


# Test validate_rationale

def test_validate_rationale_valid():
    """Test rationale validation for valid input."""
    from app.core.rationale import validate_rationale

    valid, error = validate_rationale("This is a great movie for relaxing.")
    assert valid is True
    assert error is None


def test_validate_rationale_too_long():
    """Test rationale validation for too long input."""
    from app.core.rationale import validate_rationale, MAX_RATIONALE_LENGTH

    long_text = "a" * (MAX_RATIONALE_LENGTH + 1)
    valid, error = validate_rationale(long_text)
    assert valid is False
    assert "too long" in error.lower()


def test_validate_rationale_spoiler():
    """Test rationale validation for spoiler content."""
    from app.core.rationale import validate_rationale

    valid, error = validate_rationale("The twist at the ending is amazing!")
    assert valid is False
    assert "spoiler" in error.lower()

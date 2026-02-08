"""Item selector for channel posts.

Selects items for posts with variety and repeat avoidance.
"""

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.logging import get_logger
from app.storage import ItemsRepo, PostsRepo

logger = get_logger(__name__)


@dataclass
class SelectedItem:
    """Item selected for a post."""

    item_id: str
    title: str
    item_type: str
    overview: str | None
    tags: dict[str, Any]
    rating: float | None
    poster_url: str | None = None


async def get_recently_posted_item_ids(
    session: AsyncSession,
    days: int | None = None,
) -> set[str]:
    """Get item IDs that were posted recently.

    Args:
        session: Database session
        days: Number of days to look back (default from config)

    Returns:
        Set of item IDs to exclude
    """
    if days is None:
        days = config.post_repeat_avoidance_days

    posts_repo = PostsRepo(session)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get recent posts
    try:
        recent_posts = await posts_repo.list_recent_posts(limit=500)
    except Exception as e:
        logger.warning(f"Could not fetch recent posts: {e}")
        return set()

    item_ids: set[str] = set()

    for post in recent_posts:
        # Check if post is within the cutoff (handle naive datetimes from SQLite)
        pub_at = post.published_at
        if pub_at:
            if pub_at.tzinfo is None:
                pub_at = pub_at.replace(tzinfo=timezone.utc)
            if pub_at < cutoff:
                continue

        # Try to get items from meta_json if available
        meta_json = getattr(post, "meta_json", None)
        if meta_json:
            try:
                meta = json.loads(meta_json) if isinstance(meta_json, str) else meta_json
                items = meta.get("items", [])
                item_ids.update(items)
            except (json.JSONDecodeError, TypeError):
                pass

    logger.debug(f"Found {len(item_ids)} recently posted items to exclude")
    return item_ids


async def select_items_for_format(
    session: AsyncSession,
    format_id: str,
    count: int = 1,
    item_type: str | None = None,
    mood_filter: str | None = None,
    exclude_ids: set[str] | None = None,
) -> list[SelectedItem]:
    """Select items for a post format.

    Args:
        session: Database session
        format_id: Post format ID
        count: Number of items to select
        item_type: Optional type filter ('movie' or 'series')
        mood_filter: Optional mood filter
        exclude_ids: Additional item IDs to exclude

    Returns:
        List of selected items
    """
    items_repo = ItemsRepo(session)

    # Get recently posted items
    recent_ids = await get_recently_posted_item_ids(session)
    all_excluded = recent_ids | (exclude_ids or set())

    # Get candidates
    candidates = await items_repo.list_candidates(
        item_type=item_type,
        exclude_ids=all_excluded if all_excluded else None,
        limit=100,
    )

    if not candidates:
        logger.warning(f"No candidates found for format {format_id}")
        return []

    # Parse tags and filter
    parsed_candidates: list[tuple[Any, dict]] = []
    for item in candidates:
        try:
            tags = json.loads(item.tags_json) if item.tags_json else {}
        except (json.JSONDecodeError, TypeError):
            tags = {}

        # Apply mood filter if specified
        if mood_filter:
            item_mood = tags.get("mood", [])
            if mood_filter not in item_mood:
                continue

        parsed_candidates.append((item, tags))

    if not parsed_candidates:
        logger.warning(f"No candidates after filtering for format {format_id}")
        return []

    # Select with variety
    selected = _select_with_variety(parsed_candidates, count)

    result = []
    for item, tags in selected:
        result.append(
            SelectedItem(
                item_id=item.item_id,
                title=item.title,
                item_type=item.type,
                overview=getattr(item, "overview", None),
                tags=tags,
                rating=getattr(item, "vote_average", None),
                poster_url=getattr(item, "poster_url", None) or None,
            )
        )

    return result


def _select_with_variety(
    candidates: list[tuple[Any, dict]],
    count: int,
) -> list[tuple[Any, dict]]:
    """Select items with tag variety.

    Tries to get items with different moods/paces for diversity.
    """
    if len(candidates) <= count:
        return candidates

    # Group by mood
    by_mood: dict[str, list[tuple[Any, dict]]] = {}
    for item, tags in candidates:
        moods = tags.get("mood", ["unknown"])
        mood = moods[0] if moods else "unknown"
        if mood not in by_mood:
            by_mood[mood] = []
        by_mood[mood].append((item, tags))

    selected: list[tuple[Any, dict]] = []
    mood_keys = list(by_mood.keys())
    random.shuffle(mood_keys)

    # Round-robin selection from different moods
    idx = 0
    while len(selected) < count and any(by_mood.values()):
        mood = mood_keys[idx % len(mood_keys)]
        if by_mood[mood]:
            selected.append(by_mood[mood].pop(0))
        idx += 1

        # Remove empty mood groups
        mood_keys = [m for m in mood_keys if by_mood[m]]

    return selected


async def select_for_one_pick(
    session: AsyncSession,
    mood: str | None = None,
) -> SelectedItem | None:
    """Select a single item for one_pick_emotion format."""
    items = await select_items_for_format(
        session,
        format_id="one_pick_emotion",
        count=1,
        mood_filter=mood,
    )
    return items[0] if items else None


async def select_for_if_liked(
    session: AsyncSession,
) -> tuple[SelectedItem, SelectedItem] | None:
    """Select two similar items for if_liked_x_then_y format.

    Returns:
        Tuple of (well-known item, recommendation) or None
    """
    items_repo = ItemsRepo(session)
    recent_ids = await get_recently_posted_item_ids(session)

    # Get high-score items (likely well-known)
    candidates = await items_repo.list_candidates(
        exclude_ids=recent_ids if recent_ids else None,
        limit=50,
    )

    if len(candidates) < 2:
        return None

    # Parse tags
    parsed: list[tuple[Any, dict]] = []
    for item in candidates:
        try:
            tags = json.loads(item.tags_json) if item.tags_json else {}
        except (json.JSONDecodeError, TypeError):
            tags = {}
        parsed.append((item, tags))

    # Sort by base_score descending
    parsed.sort(key=lambda x: x[0].base_score, reverse=True)

    # Pick X from top (well-known)
    item_x, tags_x = parsed[0]

    # Find Y with similar tags but different title
    mood_x = set(tags_x.get("mood", []))
    tone_x = set(tags_x.get("tone", []))

    best_match = None
    best_score = -1

    for item_y, tags_y in parsed[1:]:
        mood_y = set(tags_y.get("mood", []))
        tone_y = set(tags_y.get("tone", []))

        # Calculate similarity
        mood_overlap = len(mood_x & mood_y)
        tone_overlap = len(tone_x & tone_y)
        score = mood_overlap * 2 + tone_overlap

        if score > best_score:
            best_score = score
            best_match = (item_y, tags_y)

    if not best_match:
        best_match = parsed[1]

    item_y, tags_y = best_match

    return (
        SelectedItem(
            item_id=item_x.item_id,
            title=item_x.title,
            item_type=item_x.type,
            overview=getattr(item_x, "overview", None),
            tags=tags_x,
            rating=getattr(item_x, "vote_average", None),
            poster_url=getattr(item_x, "poster_url", None) or None,
        ),
        SelectedItem(
            item_id=item_y.item_id,
            title=item_y.title,
            item_type=item_y.type,
            overview=getattr(item_y, "overview", None),
            tags=tags_y,
            rating=getattr(item_y, "vote_average", None),
            poster_url=getattr(item_y, "poster_url", None) or None,
        ),
    )


async def select_for_fact(
    session: AsyncSession,
) -> SelectedItem | None:
    """Select an item with overview for fact_then_pick format."""
    items_repo = ItemsRepo(session)
    recent_ids = await get_recently_posted_item_ids(session)

    # Get candidates
    candidates = await items_repo.list_candidates(
        exclude_ids=recent_ids if recent_ids else None,
        limit=50,
    )

    # Prefer items with overview
    for item in candidates:
        overview = getattr(item, "overview", None)
        if overview and len(overview) > 50:
            try:
                tags = json.loads(item.tags_json) if item.tags_json else {}
            except (json.JSONDecodeError, TypeError):
                tags = {}

            return SelectedItem(
                item_id=item.item_id,
                title=item.title,
                item_type=item.type,
                overview=overview,
                tags=tags,
                rating=getattr(item, "vote_average", None),
                poster_url=getattr(item, "poster_url", None) or None,
            )

    # Fallback to any item
    if candidates:
        item = candidates[0]
        try:
            tags = json.loads(item.tags_json) if item.tags_json else {}
        except (json.JSONDecodeError, TypeError):
            tags = {}

        return SelectedItem(
            item_id=item.item_id,
            title=item.title,
            item_type=item.type,
            overview=getattr(item, "overview", None),
            tags=tags,
            rating=getattr(item, "vote_average", None),
            poster_url=getattr(item, "poster_url", None) or None,
        )

    return None

"""Anti-repeat logic for recommendations."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.storage import DismissedRepo, FavoritesRepo, RecsRepo


async def get_excluded_item_ids(
    session: AsyncSession,
    user_id: str,
    additional_excludes: set[str] | None = None,
    days: int | None = None,
) -> set[str]:
    """Get item IDs to exclude from recommendations.

    Excludes items recommended in the last N days, UNLESS the item
    is in the user's favorites (favorited items are always eligible).

    Args:
        session: Database session
        user_id: User ID
        additional_excludes: Additional item IDs to exclude (e.g., current item)
        days: Override for anti-repeat window (default from config)

    Returns:
        Set of item IDs to exclude
    """
    days = days or config.recs_anti_repeat_days

    recs_repo = RecsRepo(session)
    favorites_repo = FavoritesRepo(session)
    dismissed_repo = DismissedRepo(session)

    # Get recently recommended items
    recent_ids = await recs_repo.list_recent_user_item_ids(user_id, days=days)

    # Get dismissed items (permanently excluded)
    dismissed_ids = await dismissed_repo.list_dismissed_ids(user_id)

    if not recent_ids and not dismissed_ids:
        # No recent recommendations or dismissals, just return additional excludes
        return additional_excludes or set()

    # Get user's favorited items (these bypass anti-repeat)
    favorites = await favorites_repo.list_favorites(user_id, limit=500)
    favorited_ids = {fav.item_id for fav in favorites}

    # Exclude recent items that aren't favorited
    excluded = recent_ids - favorited_ids

    # Dismissed items are always excluded (even if favorited)
    excluded = excluded | dismissed_ids

    # Add any additional excludes
    if additional_excludes:
        excluded = excluded | additional_excludes

    return excluded


async def is_item_allowed(
    session: AsyncSession,
    user_id: str,
    item_id: str,
    days: int | None = None,
) -> bool:
    """Check if an item is allowed for recommendation.

    An item is allowed if:
    - It wasn't recommended recently (within anti-repeat window), OR
    - It's in the user's favorites

    Args:
        session: Database session
        user_id: User ID
        item_id: Item ID to check
        days: Override for anti-repeat window

    Returns:
        True if item is allowed
    """
    excluded = await get_excluded_item_ids(session, user_id, days=days)
    return item_id not in excluded

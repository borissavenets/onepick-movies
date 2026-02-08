"""Repository for favorites operations."""

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.storage.models import Favorite, Item


class FavoritesRepo:
    """Repository for user favorites operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_favorite(self, user_id: str, item_id: str) -> bool:
        """Add item to user's favorites.

        Args:
            user_id: User ID
            item_id: Item ID

        Returns:
            True if added, False if already exists
        """
        now = datetime.now(timezone.utc)

        insert_stmt = sqlite_insert(Favorite).values(
            user_id=user_id,
            item_id=item_id,
            created_at=now,
        )
        # Ignore conflict (already favorited)
        upsert_stmt = insert_stmt.on_conflict_do_nothing(
            index_elements=["user_id", "item_id"]
        )
        result = await self.session.execute(upsert_stmt)
        await self.session.commit()

        # rowcount > 0 means new row was inserted
        return result.rowcount > 0

    async def remove_favorite(self, user_id: str, item_id: str) -> bool:
        """Remove item from user's favorites.

        Args:
            user_id: User ID
            item_id: Item ID

        Returns:
            True if removed, False if not found
        """
        stmt = delete(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.item_id == item_id,
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def list_favorites(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[Favorite]:
        """Get user's favorites with items.

        Args:
            user_id: User ID
            limit: Maximum records to return

        Returns:
            List of Favorite instances with Item loaded
        """
        stmt = (
            select(Favorite)
            .options(joinedload(Favorite.item))
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def is_favorited(self, user_id: str, item_id: str) -> bool:
        """Check if item is in user's favorites.

        Args:
            user_id: User ID
            item_id: Item ID

        Returns:
            True if favorited, False otherwise
        """
        stmt = select(Favorite.id).where(
            Favorite.user_id == user_id,
            Favorite.item_id == item_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def count_favorites(self, user_id: str) -> int:
        """Count user's favorites.

        Args:
            user_id: User ID

        Returns:
            Favorites count
        """
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(Favorite)
            .where(Favorite.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_item_favorite_count(self, item_id: str) -> int:
        """Count how many users favorited an item.

        Args:
            item_id: Item ID

        Returns:
            Favorite count
        """
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(Favorite)
            .where(Favorite.item_id == item_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

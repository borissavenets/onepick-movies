"""Repository for dismissed items operations."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import DismissedItem


class DismissedRepo:
    """Repository for user dismissed items (already watched)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_dismissed(self, user_id: str, item_id: str) -> bool:
        """Mark item as dismissed (already watched).

        Args:
            user_id: User ID
            item_id: Item ID

        Returns:
            True if added, False if already dismissed
        """
        now = datetime.now(timezone.utc)

        insert_stmt = sqlite_insert(DismissedItem).values(
            user_id=user_id,
            item_id=item_id,
            created_at=now,
        )
        upsert_stmt = insert_stmt.on_conflict_do_nothing(
            index_elements=["user_id", "item_id"]
        )
        result = await self.session.execute(upsert_stmt)
        await self.session.commit()

        return result.rowcount > 0

    async def list_dismissed_ids(self, user_id: str) -> set[str]:
        """Get all dismissed item IDs for a user.

        Args:
            user_id: User ID

        Returns:
            Set of dismissed item IDs
        """
        stmt = select(DismissedItem.item_id).where(
            DismissedItem.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

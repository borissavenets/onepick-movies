"""Repository for recommendation operations."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.storage.json_utils import safe_json_dumps
from app.storage.models import Item, Recommendation


class RecsRepo:
    """Repository for recommendation operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_rec(
        self,
        user_id: str,
        item_id: str,
        context: dict | None = None,
    ) -> str:
        """Create a new recommendation record.

        Args:
            user_id: User ID
            item_id: Item ID
            context: Context dictionary (state, pace, format, delta flags)

        Returns:
            Generated recommendation ID (UUID)
        """
        rec_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        rec = Recommendation(
            rec_id=rec_id,
            user_id=user_id,
            item_id=item_id,
            context_json=safe_json_dumps(context or {}),
            created_at=now,
        )
        self.session.add(rec)
        await self.session.commit()
        return rec_id

    async def get_rec(self, rec_id: str) -> Recommendation | None:
        """Get recommendation by ID.

        Args:
            rec_id: Recommendation ID

        Returns:
            Recommendation instance or None
        """
        stmt = (
            select(Recommendation)
            .options(joinedload(Recommendation.item))
            .where(Recommendation.rec_id == rec_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent_user_item_ids(
        self,
        user_id: str,
        days: int = 90,
    ) -> set[str]:
        """Get item IDs recently recommended to a user.

        Args:
            user_id: User ID
            days: Number of days to look back

        Returns:
            Set of item IDs
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(Recommendation.item_id)
            .where(
                Recommendation.user_id == user_id,
                Recommendation.created_at >= since,
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        return {row[0] for row in result.all()}

    async def list_user_history(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[Recommendation]:
        """Get user's recent recommendation history with items.

        Args:
            user_id: User ID
            limit: Maximum records to return

        Returns:
            List of Recommendation instances with Item loaded
        """
        stmt = (
            select(Recommendation)
            .options(joinedload(Recommendation.item))
            .where(Recommendation.user_id == user_id)
            .order_by(Recommendation.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def count_user_recs(self, user_id: str) -> int:
        """Count recommendations for a user.

        Args:
            user_id: User ID

        Returns:
            Recommendation count
        """
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(Recommendation)
            .where(Recommendation.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def list_recs_for_item(
        self,
        item_id: str,
        limit: int = 100,
    ) -> list[Recommendation]:
        """Get recommendations for a specific item.

        Args:
            item_id: Item ID
            limit: Maximum records to return

        Returns:
            List of Recommendation instances
        """
        stmt = (
            select(Recommendation)
            .where(Recommendation.item_id == item_id)
            .order_by(Recommendation.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

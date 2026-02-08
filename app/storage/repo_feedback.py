"""Repository for feedback operations."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import Feedback


class FeedbackRepo:
    """Repository for user feedback operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_feedback(
        self,
        user_id: str,
        rec_id: str,
        action: str,
        reason: str | None = None,
    ) -> Feedback:
        """Add feedback for a recommendation.

        Args:
            user_id: User ID
            rec_id: Recommendation ID
            action: Feedback action (hit, miss, another, favorite, share, silent_drop)
            reason: Optional reason text

        Returns:
            Created Feedback instance
        """
        now = datetime.now(timezone.utc)
        feedback = Feedback(
            rec_id=rec_id,
            user_id=user_id,
            action=action,
            reason=reason,
            created_at=now,
        )
        self.session.add(feedback)
        await self.session.commit()
        await self.session.refresh(feedback)
        return feedback

    async def count_feedback(self, rec_id: str) -> int:
        """Count feedback entries for a recommendation.

        Args:
            rec_id: Recommendation ID

        Returns:
            Feedback count
        """
        stmt = (
            select(func.count())
            .select_from(Feedback)
            .where(Feedback.rec_id == rec_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_feedback_for_rec(self, rec_id: str) -> list[Feedback]:
        """Get all feedback for a recommendation.

        Args:
            rec_id: Recommendation ID

        Returns:
            List of Feedback instances
        """
        stmt = (
            select(Feedback)
            .where(Feedback.rec_id == rec_id)
            .order_by(Feedback.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_feedback_history(
        self,
        user_id: str,
        limit: int = 100,
    ) -> list[Feedback]:
        """Get user's feedback history.

        Args:
            user_id: User ID
            limit: Maximum records to return

        Returns:
            List of Feedback instances
        """
        stmt = (
            select(Feedback)
            .where(Feedback.user_id == user_id)
            .order_by(Feedback.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_user_actions(
        self,
        user_id: str,
        action: str | None = None,
    ) -> int:
        """Count user's feedback actions.

        Args:
            user_id: User ID
            action: Optional action type filter

        Returns:
            Action count
        """
        stmt = (
            select(func.count())
            .select_from(Feedback)
            .where(Feedback.user_id == user_id)
        )

        if action:
            stmt = stmt.where(Feedback.action == action)

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_action_stats(self, rec_id: str) -> dict[str, int]:
        """Get action counts for a recommendation.

        Args:
            rec_id: Recommendation ID

        Returns:
            Dictionary of action -> count
        """
        stmt = (
            select(Feedback.action, func.count().label("count"))
            .where(Feedback.rec_id == rec_id)
            .group_by(Feedback.action)
        )
        result = await self.session.execute(stmt)
        return {row.action: row.count for row in result.all()}

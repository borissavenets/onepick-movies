"""Repository for A/B test winner operations."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import ABWinner


class ABWinnersRepo:
    """Repository for A/B test winner lock operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_winner(
        self,
        hypothesis_id: str,
        now_dt: datetime | None = None,
    ) -> ABWinner | None:
        """Get the active winner for a hypothesis.

        Args:
            hypothesis_id: Hypothesis ID
            now_dt: Current time (defaults to now)

        Returns:
            ABWinner instance if active, None otherwise
        """
        if now_dt is None:
            now_dt = datetime.now(timezone.utc)

        stmt = (
            select(ABWinner)
            .where(
                ABWinner.hypothesis_id == hypothesis_id,
                ABWinner.starts_at <= now_dt,
                ABWinner.ends_at > now_dt,
            )
            .order_by(ABWinner.ends_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_winner(
        self,
        hypothesis_id: str,
        winner_variant_id: str,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
    ) -> ABWinner:
        """Set a winner for a hypothesis.

        Args:
            hypothesis_id: Hypothesis ID
            winner_variant_id: Winning variant ID
            starts_at: Start time (defaults to now)
            ends_at: End time (defaults to 7 days from start)

        Returns:
            Created ABWinner instance
        """
        from datetime import timedelta

        if starts_at is None:
            starts_at = datetime.now(timezone.utc)

        if ends_at is None:
            ends_at = starts_at + timedelta(days=7)

        winner = ABWinner(
            hypothesis_id=hypothesis_id,
            winner_variant_id=winner_variant_id,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        self.session.add(winner)
        await self.session.commit()
        await self.session.refresh(winner)
        return winner

    async def list_winners_for_hypothesis(
        self,
        hypothesis_id: str,
        limit: int = 10,
    ) -> list[ABWinner]:
        """List all winners for a hypothesis (including expired).

        Args:
            hypothesis_id: Hypothesis ID
            limit: Maximum records to return

        Returns:
            List of ABWinner instances
        """
        stmt = (
            select(ABWinner)
            .where(ABWinner.hypothesis_id == hypothesis_id)
            .order_by(ABWinner.ends_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_winners(
        self,
        now_dt: datetime | None = None,
    ) -> list[ABWinner]:
        """List all currently active winners.

        Args:
            now_dt: Current time (defaults to now)

        Returns:
            List of active ABWinner instances
        """
        if now_dt is None:
            now_dt = datetime.now(timezone.utc)

        stmt = (
            select(ABWinner)
            .where(
                ABWinner.starts_at <= now_dt,
                ABWinner.ends_at > now_dt,
            )
            .order_by(ABWinner.ends_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def expire_winner(self, winner_id: int) -> bool:
        """Expire a winner immediately.

        Args:
            winner_id: Winner record ID

        Returns:
            True if expired, False if not found
        """
        from sqlalchemy import update

        now = datetime.now(timezone.utc)
        stmt = (
            update(ABWinner)
            .where(ABWinner.id == winner_id)
            .values(ends_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

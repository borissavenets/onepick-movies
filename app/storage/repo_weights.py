"""Repository for user weight operations."""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import UserWeight


class WeightsRepo:
    """Repository for user preference weight operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_weight(self, user_id: str, key: str) -> int:
        """Get weight value for a user/key pair.

        Args:
            user_id: User ID
            key: Weight key (e.g., "state:escape|pace:fast")

        Returns:
            Weight value, defaults to 0 if not found
        """
        stmt = select(UserWeight.weight).where(
            UserWeight.user_id == user_id,
            UserWeight.key == key,
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return row if row is not None else 0

    async def get_all_weights(self, user_id: str) -> dict[str, int]:
        """Get all weights for a user.

        Args:
            user_id: User ID

        Returns:
            Dictionary of key -> weight
        """
        stmt = select(UserWeight.key, UserWeight.weight).where(
            UserWeight.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return {row.key: row.weight for row in result.all()}

    async def add_weight_delta(self, user_id: str, key: str, delta: int) -> None:
        """Add delta to a weight value (upsert).

        Args:
            user_id: User ID
            key: Weight key
            delta: Value to add (can be negative)
        """
        now = datetime.now(timezone.utc)

        # Try to update existing
        update_stmt = (
            update(UserWeight)
            .where(UserWeight.user_id == user_id, UserWeight.key == key)
            .values(weight=UserWeight.weight + delta, updated_at=now)
        )
        result = await self.session.execute(update_stmt)

        if result.rowcount == 0:
            # Insert new row
            insert_stmt = sqlite_insert(UserWeight).values(
                user_id=user_id,
                key=key,
                weight=delta,
                updated_at=now,
            )
            # On conflict, add delta to existing weight
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["user_id", "key"],
                set_={
                    "weight": UserWeight.weight + delta,
                    "updated_at": now,
                },
            )
            await self.session.execute(upsert_stmt)

        await self.session.commit()

    async def bulk_add_weight_deltas(
        self, user_id: str, deltas: dict[str, int]
    ) -> None:
        """Add deltas to multiple weights in one operation.

        Args:
            user_id: User ID
            deltas: Dictionary of key -> delta
        """
        if not deltas:
            return

        now = datetime.now(timezone.utc)

        for key, delta in deltas.items():
            if delta == 0:
                continue

            insert_stmt = sqlite_insert(UserWeight).values(
                user_id=user_id,
                key=key,
                weight=delta,
                updated_at=now,
            )
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["user_id", "key"],
                set_={
                    "weight": UserWeight.weight + delta,
                    "updated_at": now,
                },
            )
            await self.session.execute(upsert_stmt)

        await self.session.commit()

    async def set_weight(self, user_id: str, key: str, value: int) -> None:
        """Set absolute weight value (upsert).

        Args:
            user_id: User ID
            key: Weight key
            value: Absolute weight value
        """
        now = datetime.now(timezone.utc)

        insert_stmt = sqlite_insert(UserWeight).values(
            user_id=user_id,
            key=key,
            weight=value,
            updated_at=now,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["user_id", "key"],
            set_={
                "weight": value,
                "updated_at": now,
            },
        )
        await self.session.execute(upsert_stmt)
        await self.session.commit()

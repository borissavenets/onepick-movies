"""Repository for user operations."""

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import User, UserWeight


class UsersRepo:
    """Repository for user CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_user(self, user_id: str) -> User:
        """Get existing user or create a new one.

        Args:
            user_id: Telegram user ID as string

        Returns:
            User instance (new or existing)
        """
        stmt = select(User).where(User.user_id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is not None:
            return user

        now = datetime.now(timezone.utc)
        user = User(
            user_id=user_id,
            created_at=now,
            last_seen_at=now,
            reset_at=None,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_last_seen(self, user_id: str) -> None:
        """Update user's last seen timestamp.

        Args:
            user_id: Telegram user ID as string
        """
        now = datetime.now(timezone.utc)
        stmt = update(User).where(User.user_id == user_id).values(last_seen_at=now)
        await self.session.execute(stmt)
        await self.session.commit()

    async def reset_user(self, user_id: str) -> None:
        """Reset user preferences (clears weights, keeps history).

        Args:
            user_id: Telegram user ID as string
        """
        now = datetime.now(timezone.utc)

        # Delete all user weights
        delete_stmt = delete(UserWeight).where(UserWeight.user_id == user_id)
        await self.session.execute(delete_stmt)

        # Set reset timestamp
        update_stmt = update(User).where(User.user_id == user_id).values(reset_at=now)
        await self.session.execute(update_stmt)

        await self.session.commit()

    async def get_user(self, user_id: str) -> User | None:
        """Get user by ID.

        Args:
            user_id: Telegram user ID as string

        Returns:
            User instance or None
        """
        stmt = select(User).where(User.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def ensure_user(self, user_id: str) -> User:
        """Ensure user exists and update last_seen.

        Combines get_or_create with last_seen update.

        Args:
            user_id: Telegram user ID as string

        Returns:
            User instance
        """
        user = await self.get_or_create_user(user_id)
        await self.update_last_seen(user_id)
        return user

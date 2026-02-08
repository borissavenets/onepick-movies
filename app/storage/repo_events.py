"""Repository for event logging operations."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.json_utils import safe_json_dumps
from app.storage.models import Event


class EventsRepo:
    """Repository for event logging operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_event(
        self,
        event_name: str,
        user_id: str | None = None,
        rec_id: str | None = None,
        post_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        """Log an event.

        Args:
            event_name: Event name/type
            user_id: Optional user ID
            rec_id: Optional recommendation ID
            post_id: Optional post ID
            payload: Optional payload dictionary

        Returns:
            Created Event instance
        """
        now = datetime.now(timezone.utc)

        event = Event(
            event_name=event_name,
            user_id=user_id,
            rec_id=rec_id,
            post_id=post_id,
            payload_json=safe_json_dumps(payload or {}),
            created_at=now,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def list_events(
        self,
        event_name: str | None = None,
        user_id: str | None = None,
        since_dt: datetime | None = None,
        limit: int = 200,
    ) -> list[Event]:
        """List events with optional filters.

        Args:
            event_name: Filter by event name
            user_id: Filter by user ID
            since_dt: Filter by timestamp (after)
            limit: Maximum events to return

        Returns:
            List of Event instances
        """
        stmt = select(Event)

        if event_name:
            stmt = stmt.where(Event.event_name == event_name)

        if user_id:
            stmt = stmt.where(Event.user_id == user_id)

        if since_dt:
            stmt = stmt.where(Event.created_at >= since_dt)

        stmt = stmt.order_by(Event.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_events(
        self,
        event_name: str | None = None,
        user_id: str | None = None,
        since_dt: datetime | None = None,
    ) -> int:
        """Count events with optional filters.

        Args:
            event_name: Filter by event name
            user_id: Filter by user ID
            since_dt: Filter by timestamp (after)

        Returns:
            Event count
        """
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Event)

        if event_name:
            stmt = stmt.where(Event.event_name == event_name)

        if user_id:
            stmt = stmt.where(Event.user_id == user_id)

        if since_dt:
            stmt = stmt.where(Event.created_at >= since_dt)

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_recent_user_events(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[Event]:
        """Get recent events for a user.

        Args:
            user_id: User ID
            limit: Maximum events to return

        Returns:
            List of Event instances
        """
        stmt = (
            select(Event)
            .where(Event.user_id == user_id)
            .order_by(Event.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_events_for_rec(
        self,
        rec_id: str,
        limit: int = 50,
    ) -> list[Event]:
        """Get events related to a recommendation.

        Args:
            rec_id: Recommendation ID
            limit: Maximum events to return

        Returns:
            List of Event instances
        """
        stmt = (
            select(Event)
            .where(Event.rec_id == rec_id)
            .order_by(Event.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_events_for_post(
        self,
        post_id: str,
        limit: int = 50,
    ) -> list[Event]:
        """Get events related to a post.

        Args:
            post_id: Post ID
            limit: Maximum events to return

        Returns:
            List of Event instances
        """
        stmt = (
            select(Event)
            .where(Event.post_id == post_id)
            .order_by(Event.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

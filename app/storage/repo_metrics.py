"""Repository for post metrics operations."""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.storage.models import Post, PostMetric


class MetricsRepo:
    """Repository for post metrics operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_snapshot(
        self,
        post_id: str,
        captured_at: datetime | None = None,
        views: int = 0,
        reactions: int = 0,
        forwards: int = 0,
        bot_clicks: int = 0,
        unsub_delta: int = 0,
        score: float | None = None,
    ) -> PostMetric:
        """Insert a metrics snapshot for a post.

        Args:
            post_id: Post ID
            captured_at: Capture timestamp (defaults to now)
            views: View count
            reactions: Reaction count
            forwards: Forward count
            bot_clicks: Bot click count
            unsub_delta: Unsubscribe delta
            score: Calculated score (optional)

        Returns:
            Created PostMetric instance
        """
        if captured_at is None:
            captured_at = datetime.now(timezone.utc)

        metric = PostMetric(
            post_id=post_id,
            captured_at=captured_at,
            views=views,
            reactions=reactions,
            forwards=forwards,
            bot_clicks=bot_clicks,
            unsub_delta=unsub_delta,
            score=score,
        )
        self.session.add(metric)
        await self.session.commit()
        await self.session.refresh(metric)
        return metric

    async def update_score(
        self,
        post_id: str,
        captured_at: datetime,
        score: float,
    ) -> bool:
        """Update score for a specific snapshot.

        Args:
            post_id: Post ID
            captured_at: Snapshot timestamp
            score: New score value

        Returns:
            True if updated, False if not found
        """
        stmt = (
            update(PostMetric)
            .where(
                PostMetric.post_id == post_id,
                PostMetric.captured_at == captured_at,
            )
            .values(score=score)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def get_latest_snapshot(self, post_id: str) -> PostMetric | None:
        """Get the most recent metrics snapshot for a post.

        Args:
            post_id: Post ID

        Returns:
            PostMetric instance or None
        """
        stmt = (
            select(PostMetric)
            .where(PostMetric.post_id == post_id)
            .order_by(PostMetric.captured_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_snapshots_for_post(
        self,
        post_id: str,
        since_dt: datetime | None = None,
        limit: int = 100,
    ) -> list[PostMetric]:
        """List metrics snapshots for a post.

        Args:
            post_id: Post ID
            since_dt: Only include snapshots after this time
            limit: Maximum snapshots to return

        Returns:
            List of PostMetric instances
        """
        stmt = select(PostMetric).where(PostMetric.post_id == post_id)

        if since_dt:
            stmt = stmt.where(PostMetric.captured_at >= since_dt)

        stmt = stmt.order_by(PostMetric.captured_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_latest_snapshots(
        self,
        limit: int = 100,
    ) -> list[tuple[Post, PostMetric | None]]:
        """Get latest snapshot for all posts.

        Args:
            limit: Maximum posts to return

        Returns:
            List of (Post, PostMetric or None) tuples
        """
        # Get recent posts
        posts_stmt = (
            select(Post)
            .order_by(Post.published_at.desc())
            .limit(limit)
        )
        posts_result = await self.session.execute(posts_stmt)
        posts = list(posts_result.scalars().all())

        results = []
        for post in posts:
            metric = await self.get_latest_snapshot(post.post_id)
            results.append((post, metric))

        return results

    async def calculate_growth_rate(
        self,
        post_id: str,
        hours: int = 24,
    ) -> dict[str, float] | None:
        """Calculate growth rates for a post over a time period.

        Args:
            post_id: Post ID
            hours: Time period in hours

        Returns:
            Dictionary with growth rates, or None if insufficient data
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=hours)

        snapshots = await self.list_snapshots_for_post(post_id, since_dt=since)

        if len(snapshots) < 2:
            return None

        latest = snapshots[0]
        oldest = snapshots[-1]

        time_diff = (latest.captured_at - oldest.captured_at).total_seconds() / 3600

        if time_diff < 0.1:  # Less than 6 minutes
            return None

        return {
            "views_per_hour": (latest.views - oldest.views) / time_diff,
            "reactions_per_hour": (latest.reactions - oldest.reactions) / time_diff,
            "forwards_per_hour": (latest.forwards - oldest.forwards) / time_diff,
            "bot_clicks_per_hour": (latest.bot_clicks - oldest.bot_clicks) / time_diff,
        }

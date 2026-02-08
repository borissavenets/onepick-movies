"""Repository for post operations."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import Post


class PostsRepo:
    """Repository for channel post operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_post(
        self,
        post_id: str,
        format_id: str,
        hypothesis_id: str,
        variant_id: str,
        text: str,
        meta_json: str = "{}",
        published_at: datetime | None = None,
    ) -> Post:
        """Create a new post record.

        Args:
            post_id: Unique post ID (e.g., Telegram message ID)
            format_id: Format template ID
            hypothesis_id: A/B hypothesis ID
            variant_id: Variant ID within hypothesis
            text: Post text content
            meta_json: JSON metadata (items, cta flag, etc.)
            published_at: Publication timestamp (defaults to now)

        Returns:
            Created Post instance
        """
        if published_at is None:
            published_at = datetime.now(timezone.utc)

        post = Post(
            post_id=post_id,
            format_id=format_id,
            hypothesis_id=hypothesis_id,
            variant_id=variant_id,
            text=text,
            meta_json=meta_json,
            published_at=published_at,
        )
        self.session.add(post)
        await self.session.commit()
        await self.session.refresh(post)
        return post

    async def get_post(self, post_id: str) -> Post | None:
        """Get post by ID.

        Args:
            post_id: Post ID

        Returns:
            Post instance or None
        """
        stmt = select(Post).where(Post.post_id == post_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent_posts(
        self,
        days: int = 60,
        limit: int = 100,
    ) -> list[Post]:
        """List recent posts.

        Args:
            days: Number of days to look back
            limit: Maximum posts to return

        Returns:
            List of Post instances
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(Post)
            .where(Post.published_at >= since)
            .order_by(Post.published_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_posts_by_hypothesis(
        self,
        hypothesis_id: str,
        limit: int = 50,
    ) -> list[Post]:
        """List posts for a specific hypothesis.

        Args:
            hypothesis_id: Hypothesis ID
            limit: Maximum posts to return

        Returns:
            List of Post instances
        """
        stmt = (
            select(Post)
            .where(Post.hypothesis_id == hypothesis_id)
            .order_by(Post.published_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_posts_by_variant(
        self,
        hypothesis_id: str,
        variant_id: str,
        limit: int = 50,
    ) -> list[Post]:
        """List posts for a specific variant.

        Args:
            hypothesis_id: Hypothesis ID
            variant_id: Variant ID
            limit: Maximum posts to return

        Returns:
            List of Post instances
        """
        stmt = (
            select(Post)
            .where(
                Post.hypothesis_id == hypothesis_id,
                Post.variant_id == variant_id,
            )
            .order_by(Post.published_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_telegram_message_id(self, tg_msg_id: str) -> Post | None:
        """Find post by Telegram message ID stored in meta_json.

        Args:
            tg_msg_id: Telegram message ID string

        Returns:
            Post instance or None
        """
        import json

        recent = await self.list_recent_posts(days=30, limit=200)
        for post in recent:
            try:
                meta = json.loads(post.meta_json) if isinstance(post.meta_json, str) else {}
                if str(meta.get("telegram_message_id")) == str(tg_msg_id):
                    return post
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    async def count_posts(self) -> int:
        """Count total posts.

        Returns:
            Post count
        """
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Post)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

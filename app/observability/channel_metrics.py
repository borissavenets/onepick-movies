"""Daily channel KPIs: posts published, avg post score, bot clicks per format."""

from datetime import datetime, timedelta, timezone

from app.logging import get_logger

logger = get_logger(__name__)


async def compute_channel_metrics(
    date_str: str | None = None,
) -> dict[str, float]:
    """Compute daily channel KPIs for a given date.

    Metrics:
        - posts_published: count of posts published that day
        - avg_post_score: average score of scored posts from that day
        - total_bot_clicks: sum of bot_clicks from latest snapshots
        - bot_clicks_{format_id}: clicks broken out by format

    Args:
        date_str: Date in YYYY-MM-DD format (defaults to yesterday).

    Returns:
        Dict of metric_name -> value.
    """
    import json

    from sqlalchemy import func, select

    from app.storage import get_session_factory
    from app.storage.models import Post, PostMetric

    if date_str is None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

    day_start = datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
    day_end = day_start + timedelta(days=1)

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Posts published that day
        posts_stmt = (
            select(Post)
            .where(
                Post.published_at >= day_start,
                Post.published_at < day_end,
            )
        )
        posts_result = await session.execute(posts_stmt)
        posts = list(posts_result.scalars().all())

        posts_published = len(posts)

        # Gather scores and clicks per format
        scores: list[float] = []
        total_bot_clicks = 0
        clicks_by_format: dict[str, int] = {}

        for post in posts:
            # Get latest snapshot
            snap_stmt = (
                select(PostMetric)
                .where(PostMetric.post_id == post.post_id)
                .order_by(PostMetric.captured_at.desc())
                .limit(1)
            )
            snap_result = await session.execute(snap_stmt)
            snap = snap_result.scalar_one_or_none()

            if snap:
                if snap.score is not None:
                    scores.append(snap.score)
                total_bot_clicks += snap.bot_clicks

                fmt = post.format_id
                clicks_by_format[fmt] = clicks_by_format.get(fmt, 0) + snap.bot_clicks

    avg_score = sum(scores) / len(scores) if scores else 0.0

    metrics: dict[str, float] = {
        "channel_posts_published": float(posts_published),
        "channel_avg_post_score": round(avg_score, 2),
        "channel_total_bot_clicks": float(total_bot_clicks),
    }

    for fmt, clicks in clicks_by_format.items():
        metrics[f"channel_clicks_{fmt}"] = float(clicks)

    logger.info(
        f"Channel metrics {date_str}: posts={posts_published}, "
        f"avg_score={avg_score:.1f}, clicks={total_bot_clicks}"
    )

    return metrics

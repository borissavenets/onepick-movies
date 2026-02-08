"""System health metrics: last post age, last TMDB sync age, error counts."""

from datetime import datetime, timedelta, timezone

from app.logging import get_logger

logger = get_logger(__name__)


async def compute_system_metrics() -> dict[str, float]:
    """Compute current system health metrics.

    Metrics:
        - last_post_age_hours: hours since last published post
        - last_tmdb_sync_age_hours: hours since last tmdb_sync_completed event
        - errors_24h: count of error-level events in last 24 hours
        - total_items: total items in catalog
        - total_users: total registered users

    Returns:
        Dict of metric_name -> value.
    """
    from sqlalchemy import func, select

    from app.storage import get_session_factory
    from app.storage.models import Event, Item, Post, User

    now = datetime.now(timezone.utc)
    session_factory = get_session_factory()

    async with session_factory() as session:
        # Last post age
        last_post_stmt = (
            select(Post.published_at)
            .order_by(Post.published_at.desc())
            .limit(1)
        )
        last_post_result = await session.execute(last_post_stmt)
        last_post_at = last_post_result.scalar_one_or_none()

        if last_post_at:
            last_post_at = _ensure_utc(last_post_at)
            last_post_age_hours = (now - last_post_at).total_seconds() / 3600
        else:
            last_post_age_hours = -1.0  # no posts yet

        # Last TMDB sync age
        last_sync_stmt = (
            select(Event.created_at)
            .where(Event.event_name == "tmdb_sync_completed")
            .order_by(Event.created_at.desc())
            .limit(1)
        )
        last_sync_result = await session.execute(last_sync_stmt)
        last_sync_at = last_sync_result.scalar_one_or_none()

        if last_sync_at:
            last_sync_at = _ensure_utc(last_sync_at)
            last_tmdb_sync_age_hours = (now - last_sync_at).total_seconds() / 3600
        else:
            last_tmdb_sync_age_hours = -1.0

        # Error events in last 24h
        cutoff_24h = now - timedelta(hours=24)
        errors_stmt = (
            select(func.count())
            .select_from(Event)
            .where(
                Event.event_name.like("%error%"),
                Event.created_at >= cutoff_24h,
            )
        )
        errors_result = await session.execute(errors_stmt)
        errors_24h = errors_result.scalar() or 0

        # Total items
        items_stmt = select(func.count()).select_from(Item)
        items_result = await session.execute(items_stmt)
        total_items = items_result.scalar() or 0

        # Total users
        users_stmt = select(func.count()).select_from(User)
        users_result = await session.execute(users_stmt)
        total_users = users_result.scalar() or 0

    metrics = {
        "sys_last_post_age_hours": round(last_post_age_hours, 2),
        "sys_last_tmdb_sync_age_hours": round(last_tmdb_sync_age_hours, 2),
        "sys_errors_24h": float(errors_24h),
        "sys_total_items": float(total_items),
        "sys_total_users": float(total_users),
    }

    logger.info(
        f"System metrics: post_age={last_post_age_hours:.1f}h, "
        f"sync_age={last_tmdb_sync_age_hours:.1f}h, errors={errors_24h}"
    )

    return metrics


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

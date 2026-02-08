"""Daily bot KPIs: sessions, DAU, hit_rate, miss_rate."""

from datetime import datetime, timedelta, timezone

from app.logging import get_logger

logger = get_logger(__name__)


async def compute_bot_metrics(
    date_str: str | None = None,
) -> dict[str, float]:
    """Compute daily bot KPIs for a given date.

    Metrics:
        - sessions: count of bot_start events
        - dau: distinct users with any event
        - hit_rate: hit / (hit + miss + another)
        - miss_rate: miss / (hit + miss + another)
        - favorites: total favorite actions
        - shares: total share actions

    Args:
        date_str: Date in YYYY-MM-DD format (defaults to yesterday).

    Returns:
        Dict of metric_name -> value.
    """
    from sqlalchemy import func, select

    from app.storage import get_session_factory
    from app.storage.models import Event, Feedback

    if date_str is None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

    day_start = datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
    day_end = day_start + timedelta(days=1)

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Sessions (bot_start events)
        sessions_stmt = (
            select(func.count())
            .select_from(Event)
            .where(
                Event.event_name == "bot_start",
                Event.created_at >= day_start,
                Event.created_at < day_end,
            )
        )
        sessions_result = await session.execute(sessions_stmt)
        sessions = sessions_result.scalar() or 0

        # DAU (distinct users with any event)
        dau_stmt = (
            select(func.count(func.distinct(Event.user_id)))
            .select_from(Event)
            .where(
                Event.user_id.isnot(None),
                Event.created_at >= day_start,
                Event.created_at < day_end,
            )
        )
        dau_result = await session.execute(dau_stmt)
        dau = dau_result.scalar() or 0

        # Feedback action counts
        action_counts: dict[str, int] = {}
        for action in ("hit", "miss", "another", "favorite", "share"):
            stmt = (
                select(func.count())
                .select_from(Feedback)
                .where(
                    Feedback.action == action,
                    Feedback.created_at >= day_start,
                    Feedback.created_at < day_end,
                )
            )
            result = await session.execute(stmt)
            action_counts[action] = result.scalar() or 0

    total_decisions = (
        action_counts["hit"] + action_counts["miss"] + action_counts["another"]
    )
    hit_rate = action_counts["hit"] / total_decisions if total_decisions > 0 else 0.0
    miss_rate = action_counts["miss"] / total_decisions if total_decisions > 0 else 0.0

    metrics = {
        "bot_sessions": float(sessions),
        "bot_dau": float(dau),
        "bot_hit_rate": round(hit_rate, 4),
        "bot_miss_rate": round(miss_rate, 4),
        "bot_favorites": float(action_counts["favorite"]),
        "bot_shares": float(action_counts["share"]),
    }

    logger.info(
        f"Bot metrics {date_str}: sessions={sessions}, DAU={dau}, "
        f"hit_rate={hit_rate:.2%}, miss_rate={miss_rate:.2%}"
    )

    return metrics

"""SLO tracking — Time-to-First-Recommendation (TTFR) p50/p90.

TTFR is measured as the time between a ``bot_start`` event and the first
``recommendation_shown`` event for the same user, within a 30-minute window.
"""

from datetime import datetime, timedelta, timezone

from app.logging import get_logger

logger = get_logger(__name__)

TTFR_SESSION_WINDOW_MINUTES = 30


def percentile(values: list[float], p: float) -> float:
    """Compute the p-th percentile of a list of values.

    Uses the nearest-rank method.

    Args:
        values: Non-empty list of numeric values.
        p: Percentile in range [0, 100].

    Returns:
        The percentile value.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = max(0, min(int(len(sorted_vals) * p / 100.0 + 0.5) - 1, len(sorted_vals) - 1))
    return sorted_vals[k]


async def compute_ttfr(
    date_str: str | None = None,
) -> dict:
    """Compute TTFR p50 and p90 for a given date.

    Pairs ``bot_start`` events with the next ``recommendation_shown`` event
    for the same user within 30 minutes.

    Args:
        date_str: Date in YYYY-MM-DD format (defaults to yesterday).

    Returns:
        Dict with p50, p90, sample_count, and individual durations.
    """
    from app.storage import EventsRepo, get_session_factory

    if date_str is None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

    day_start = datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
    day_end = day_start + timedelta(days=1)

    session_factory = get_session_factory()
    async with session_factory() as session:
        events_repo = EventsRepo(session)

        starts = await events_repo.list_events(
            event_name="bot_start",
            since_dt=day_start,
            limit=5000,
        )
        # Filter to only events within the target day
        starts = [
            e for e in starts
            if _ensure_utc(e.created_at) < day_end
        ]

        recs = await events_repo.list_events(
            event_name="recommendation_shown",
            since_dt=day_start,
            limit=10000,
        )
        recs = [
            e for e in recs
            if _ensure_utc(e.created_at) < day_end + timedelta(minutes=TTFR_SESSION_WINDOW_MINUTES)
        ]

    # Build lookup: user_id -> sorted list of rec timestamps
    from collections import defaultdict
    recs_by_user: dict[str, list[datetime]] = defaultdict(list)
    for r in recs:
        if r.user_id:
            recs_by_user[r.user_id].append(_ensure_utc(r.created_at))

    for uid in recs_by_user:
        recs_by_user[uid].sort()

    # Match each bot_start with the first rec within the window
    durations: list[float] = []
    for start_event in starts:
        uid = start_event.user_id
        if not uid or uid not in recs_by_user:
            continue

        start_ts = _ensure_utc(start_event.created_at)
        window_end = start_ts + timedelta(minutes=TTFR_SESSION_WINDOW_MINUTES)

        # Find first rec timestamp >= start_ts and <= window_end
        for rec_ts in recs_by_user[uid]:
            if rec_ts < start_ts:
                continue
            if rec_ts > window_end:
                break
            duration_seconds = (rec_ts - start_ts).total_seconds()
            durations.append(duration_seconds)
            break

    p50 = percentile(durations, 50) if durations else 0.0
    p90 = percentile(durations, 90) if durations else 0.0

    logger.info(
        f"TTFR {date_str}: p50={p50:.1f}s, p90={p90:.1f}s, "
        f"samples={len(durations)}"
    )

    return {
        "date": date_str,
        "p50": round(p50, 2),
        "p90": round(p90, 2),
        "sample_count": len(durations),
    }


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

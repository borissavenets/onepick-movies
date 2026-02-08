"""Compute post_score for recent posts.

Runs every 6 hours.  For each post published within the A/B evaluation
window that has at least one metrics snapshot, pick the best snapshot and
apply the scoring formula::

    score = reactions*2 + forwards*3 + bot_clicks*4 - unsub_delta*5
"""

from datetime import datetime, timedelta, timezone

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC).  SQLite stores naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def calculate_score(
    reactions: int,
    forwards: int,
    bot_clicks: int,
    unsub_delta: int,
) -> float:
    """Apply the MVP scoring formula."""
    return float(
        reactions * 2
        + forwards * 3
        + bot_clicks * 4
        - unsub_delta * 5
    )


async def run_compute_scores() -> dict:
    """Score recent posts and persist results.

    Returns:
        Summary dict with counts of scored posts.
    """
    from app.storage import (
        EventsRepo,
        MetricsRepo,
        PostsRepo,
        get_session_factory,
    )

    now = datetime.now(timezone.utc)
    max_age = timedelta(hours=config.ab_eval_max_hours)
    min_age = timedelta(hours=config.ab_eval_min_hours)
    target_offset = timedelta(hours=config.score_window_hours)

    session_factory = get_session_factory()
    scored = 0

    async with session_factory() as session:
        posts_repo = PostsRepo(session)
        metrics_repo = MetricsRepo(session)
        events_repo = EventsRepo(session)

        # Posts published between (now - max_age) and (now - min_age)
        # so they've had at least min_age hours to accumulate metrics.
        candidates = await posts_repo.list_recent_posts(
            days=int(max_age.total_seconds() / 86400) + 1,
            limit=200,
        )

        for post in candidates:
            if not post.published_at:
                continue

            pub_at = _ensure_utc(post.published_at)
            age = now - pub_at
            if age < min_age or age > max_age:
                continue

            snapshots = await metrics_repo.list_snapshots_for_post(
                post.post_id, limit=50,
            )
            if not snapshots:
                continue

            # Pick snapshot closest to target_offset after published_at
            target_ts = pub_at + target_offset
            best = None
            best_delta = None

            for snap in snapshots:
                snap_at = _ensure_utc(snap.captured_at)
                snap_offset = snap_at - pub_at
                if snap_offset < min_age:
                    continue
                delta = abs((snap_at - target_ts).total_seconds())
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    best = snap

            # Fallback: latest snapshot that is at least min_age old
            if best is None:
                for snap in snapshots:
                    snap_offset = _ensure_utc(snap.captured_at) - pub_at
                    if snap_offset >= min_age:
                        best = snap
                        break

            if best is None:
                continue

            score = calculate_score(
                reactions=best.reactions,
                forwards=best.forwards,
                bot_clicks=best.bot_clicks,
                unsub_delta=best.unsub_delta,
            )

            await metrics_repo.update_score(
                post_id=post.post_id,
                captured_at=best.captured_at,
                score=score,
            )

            await events_repo.log_event(
                event_name="post_score_computed",
                post_id=post.post_id,
                payload={
                    "score": score,
                    "snapshot_at": best.captured_at.isoformat(),
                    "reactions": best.reactions,
                    "forwards": best.forwards,
                    "bot_clicks": best.bot_clicks,
                    "unsub_delta": best.unsub_delta,
                },
            )

            scored += 1

    logger.info(f"compute_scores: scored {scored} posts")
    return {"scored": scored}

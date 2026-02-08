"""Aggregate bot-click events into post_metrics snapshots.

Runs hourly.  Reads ``bot_click_from_post`` events since the last run,
groups by ``post_id``, and upserts the ``bot_clicks`` counter in
``post_metrics``.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

from app.logging import get_logger

logger = get_logger(__name__)

# Module-level bookmark so we only process new events each run.
_last_run_at: datetime | None = None


async def run_bot_clicks_aggregator() -> dict:
    """Count bot_click_from_post events and upsert post_metrics.bot_clicks.

    Returns:
        Summary dict with counts.
    """
    global _last_run_at

    from app.storage import EventsRepo, MetricsRepo, get_session_factory
    from app.storage.json_utils import safe_json_loads

    now = datetime.now(timezone.utc)
    since = _last_run_at or (now - timedelta(hours=1))

    session_factory = get_session_factory()

    async with session_factory() as session:
        events_repo = EventsRepo(session)
        events = await events_repo.list_events(
            event_name="bot_click_from_post",
            since_dt=since,
            limit=5000,
        )

        if not events:
            logger.debug("bot_clicks_aggregator: no new click events")
            _last_run_at = now
            return {"processed": 0}

        # Group clicks by post_id
        clicks: Counter[str] = Counter()
        for ev in events:
            payload = safe_json_loads(ev.payload_json)
            post_id = payload.get("post_id")
            if post_id:
                clicks[post_id] += 1

        metrics_repo = MetricsRepo(session)

        # Truncate to current hour for the snapshot timestamp
        hour_ts = now.replace(minute=0, second=0, microsecond=0)

        for post_id, count in clicks.items():
            existing = await metrics_repo.get_latest_snapshot(post_id)
            if existing and existing.captured_at == hour_ts:
                # Update in-place
                existing.bot_clicks = (existing.bot_clicks or 0) + count
                await session.commit()
            else:
                # Carry forward other counters from the latest snapshot
                prev_views = existing.views if existing else 0
                prev_reactions = existing.reactions if existing else 0
                prev_forwards = existing.forwards if existing else 0
                prev_unsub = existing.unsub_delta if existing else 0
                prev_clicks = existing.bot_clicks if existing else 0

                await metrics_repo.insert_snapshot(
                    post_id=post_id,
                    captured_at=hour_ts,
                    views=prev_views,
                    reactions=prev_reactions,
                    forwards=prev_forwards,
                    bot_clicks=prev_clicks + count,
                    unsub_delta=prev_unsub,
                )

        logger.info(
            f"bot_clicks_aggregator: {len(events)} events -> "
            f"{len(clicks)} posts updated"
        )

    _last_run_at = now
    return {"processed": len(events), "posts_updated": len(clicks)}

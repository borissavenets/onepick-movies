"""Schedule presets and bandit selection for post timing A/B testing.

Defines preset posting schedules (time + quantity) and a bandit-lite
algorithm that learns which schedule produces the best engagement.
"""

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.logging import get_logger

logger = get_logger(__name__)

EXPLOIT_RATE = 0.70


@dataclass(frozen=True)
class SchedulePreset:
    """A posting schedule variant."""

    slots: tuple[str, ...]
    description: str


SCHEDULE_PRESETS: dict[str, SchedulePreset] = {
    "morning_evening": SchedulePreset(
        slots=("09:30", "19:30"),
        description="2 posts: morning + evening",
    ),
    "three_times": SchedulePreset(
        slots=("09:30", "13:00", "19:30"),
        description="3 posts: classic",
    ),
    "peak_hours": SchedulePreset(
        slots=("13:00", "19:30", "21:00"),
        description="3 posts: afternoon + evening",
    ),
    "twice_daily": SchedulePreset(
        slots=("12:00", "20:00"),
        description="2 posts: midday + late",
    ),
    "once_evening": SchedulePreset(
        slots=("19:30",),
        description="1 post: evening only",
    ),
}


def get_all_unique_slots() -> list[str]:
    """Return sorted list of all unique time slots across all presets."""
    slots: set[str] = set()
    for preset in SCHEDULE_PRESETS.values():
        slots.update(preset.slots)
    return sorted(slots)


def slot_in_schedule(slot_time: str, schedule_id: str) -> bool:
    """Check if a time slot belongs to the given schedule preset."""
    preset = SCHEDULE_PRESETS.get(schedule_id)
    if not preset:
        return False
    return slot_time in preset.slots


async def _avg_scores_by_schedule(session, days: int = 14) -> dict[str, float]:
    """Return average post score per schedule_id over the last N days.

    Reads schedule_id from posts.meta_json and joins with post_metrics
    to compute average scores.
    """
    from sqlalchemy import func, select, cast, String

    from app.storage.models import Post, PostMetric

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Get posts with scores from recent period
    stmt = (
        select(Post.post_id, Post.meta_json, PostMetric.score)
        .join(PostMetric, PostMetric.post_id == Post.post_id)
        .where(Post.published_at >= since, PostMetric.score.is_not(None))
    )
    result = await session.execute(stmt)
    rows = result.all()

    # Group scores by schedule_id extracted from meta_json
    schedule_scores: dict[str, list[float]] = {}
    for post_id, meta_json, score in rows:
        try:
            meta = json.loads(meta_json) if meta_json else {}
        except (json.JSONDecodeError, TypeError):
            continue

        schedule_id = meta.get("schedule_id")
        if not schedule_id or schedule_id not in SCHEDULE_PRESETS:
            continue

        schedule_scores.setdefault(schedule_id, []).append(float(score))

    return {
        sid: sum(scores) / len(scores)
        for sid, scores in schedule_scores.items()
        if scores
    }


async def pick_schedule_bandit(session) -> str:
    """Pick a schedule using bandit-lite: 70% exploit best, 30% explore.

    Returns schedule_id from SCHEDULE_PRESETS.
    """
    scores = await _avg_scores_by_schedule(session)

    if not scores:
        choice = random.choice(list(SCHEDULE_PRESETS.keys()))
        logger.info(f"Schedule bandit: no scores yet, random pick={choice}")
        return choice

    if random.random() < EXPLOIT_RATE:
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        logger.info(f"Schedule bandit: exploit best={best} (avg={scores[best]:.2f})")
        return best

    # Explore: pick from schedules that are NOT the current best
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    others = [s for s in SCHEDULE_PRESETS if s != best]
    choice = random.choice(others) if others else best
    logger.info(f"Schedule bandit: explore pick={choice}")
    return choice

"""A/B winner selection job.

Runs daily.  For each hypothesis_id with >= 2 variants in the last 14 days,
compare average post_score and lock the best variant as the winner for
``AB_DEFAULT_DURATION_DAYS``.

Anti-flip-flop: an active winner is kept unless the challenger beats it by
at least 15 %.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)

FLIP_FLOP_MARGIN = 0.15  # challenger must beat incumbent by 15 %


async def run_ab_winner_selection() -> dict:
    """Evaluate A/B hypotheses and lock winners.

    Returns:
        Summary dict with count of winners set.
    """
    from sqlalchemy import select
    from app.storage import (
        ABWinnersRepo,
        EventsRepo,
        get_session_factory,
    )
    from app.storage.models import Post, PostMetric

    now = datetime.now(timezone.utc)
    lookback = now - timedelta(days=14)

    session_factory = get_session_factory()
    winners_set = 0

    async with session_factory() as session:
        ab_repo = ABWinnersRepo(session)
        events_repo = EventsRepo(session)

        # Fetch scored posts from the last 14 days
        stmt = (
            select(
                Post.hypothesis_id,
                Post.variant_id,
                PostMetric.score,
            )
            .join(PostMetric, PostMetric.post_id == Post.post_id)
            .where(
                Post.published_at >= lookback,
                PostMetric.score.is_not(None),
            )
        )
        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            logger.debug("ab_winner: no scored posts found")
            return {"winners_set": 0}

        # Group scores by (hypothesis_id, variant_id)
        scores: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for hyp_id, var_id, score in rows:
            scores[hyp_id][var_id].append(float(score))

        for hyp_id, variants in scores.items():
            if len(variants) < 2:
                continue

            # Compute average per variant
            avgs = {
                vid: sum(vals) / len(vals)
                for vid, vals in variants.items()
            }

            best_variant = max(avgs, key=avgs.get)  # type: ignore[arg-type]
            best_avg = avgs[best_variant]

            # Check for active winner (anti-flip-flop)
            active = await ab_repo.get_active_winner(hyp_id, now_dt=now)
            if active:
                incumbent_avg = avgs.get(active.winner_variant_id, 0.0)
                # Only override if challenger exceeds by margin
                if best_variant != active.winner_variant_id:
                    threshold = incumbent_avg * (1 + FLIP_FLOP_MARGIN)
                    if best_avg <= threshold:
                        logger.debug(
                            f"ab_winner: {hyp_id} – keeping incumbent "
                            f"{active.winner_variant_id} "
                            f"(challenger {best_avg:.1f} <= "
                            f"threshold {threshold:.1f})"
                        )
                        continue
                else:
                    # Same winner, no update needed
                    continue

            ends_at = now + timedelta(days=config.ab_default_duration_days)
            await ab_repo.set_winner(
                hypothesis_id=hyp_id,
                winner_variant_id=best_variant,
                starts_at=now,
                ends_at=ends_at,
            )

            await events_repo.log_event(
                event_name="ab_winner_set",
                payload={
                    "hypothesis_id": hyp_id,
                    "winner_variant_id": best_variant,
                    "avg_score": best_avg,
                    "all_avgs": {k: round(v, 2) for k, v in avgs.items()},
                    "duration_days": config.ab_default_duration_days,
                },
            )

            winners_set += 1
            logger.info(
                f"ab_winner: {hyp_id} -> {best_variant} "
                f"(avg={best_avg:.1f})"
            )

    logger.info(f"ab_winner: {winners_set} winners set")
    return {"winners_set": winners_set}

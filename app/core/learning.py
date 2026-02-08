"""Learning/weights update logic for the recommendation system."""

import json
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tagging import context_key, context_key_partial
from app.logging import get_logger
from app.storage import EventsRepo, RecsRepo, WeightsRepo

logger = get_logger(__name__)

# Reward values for different actions
REWARDS: dict[str, int] = {
    "hit": 2,
    "another": 1,
    "miss": -2,
    "favorite": 2,
    "share": 2,
    "silent_drop": -1,
}

# Miss reason corrections
MISS_REASON_CORRECTIONS: dict[str, dict[str, int]] = {
    "tooslow": {
        # Add positive weight for faster pace
        "pace:fast": 1,
        "pace:slow": -1,
    },
    "tooheavy": {
        # Add positive weight for lighter content
        "state:light": 1,
        "state:heavy": -1,
    },
    "notvibe": {
        # Generic correction - no specific key changes
        # Will shift tone preference if tone bucket is available
    },
}


def _parse_context(context_json: str | None) -> dict[str, Any]:
    """Parse context JSON safely.

    Args:
        context_json: JSON string

    Returns:
        Parsed dict or empty dict
    """
    if not context_json:
        return {}
    try:
        return json.loads(context_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _get_opposite_pace(pace: str) -> str:
    """Get opposite pace value.

    Args:
        pace: Current pace

    Returns:
        Opposite pace
    """
    return "fast" if pace == "slow" else "slow"


def _get_opposite_state(state: str) -> str:
    """Get 'lighter' state if heavy, or 'heavier' if light.

    Args:
        state: Current state

    Returns:
        Alternative state
    """
    if state == "heavy":
        return "light"
    elif state == "light":
        return "heavy"
    return "escape"  # Neutral for escape


async def update_weights(
    session: AsyncSession,
    user_id: str,
    rec_id: str,
    action: str,
    reason: str | None = None,
) -> dict[str, int]:
    """Update user weights based on feedback.

    Args:
        session: Database session
        user_id: User ID
        rec_id: Recommendation ID
        action: Feedback action (hit, miss, another, favorite, share, silent_drop)
        reason: Optional miss reason (tooslow, tooheavy, notvibe)

    Returns:
        Dict of weight changes applied
    """
    weights_repo = WeightsRepo(session)
    events_repo = EventsRepo(session)
    recs_repo = RecsRepo(session)

    # Get the recommendation to extract context
    rec = await recs_repo.get_rec(rec_id)
    if not rec:
        logger.warning(f"Recommendation {rec_id} not found for weight update")
        return {}

    context = _parse_context(rec.context_json)

    # Build context key from recommendation context
    answers = {
        "state": context.get("state", "escape"),
        "pace": context.get("pace", "slow"),
        "format": context.get("format", "movie"),
    }
    key = context_key(answers)

    # Get base reward
    reward = REWARDS.get(action, 0)
    if reward == 0 and action not in REWARDS:
        logger.warning(f"Unknown action: {action}")
        return {}

    weight_changes: dict[str, int] = {}

    # Apply main reward
    if reward != 0:
        await weights_repo.add_weight_delta(user_id, key, reward)
        weight_changes[key] = reward
        logger.debug(f"Applied weight delta: user={user_id}, key={key}, delta={reward}")

    # Apply miss reason corrections
    if reason and reason in MISS_REASON_CORRECTIONS:
        corrections = MISS_REASON_CORRECTIONS[reason]

        if reason == "tooslow":
            # Boost preference for opposite pace
            current_pace = answers.get("pace", "slow")
            opposite_pace = _get_opposite_pace(current_pace)

            # Create key for same state but opposite pace
            alt_answers = answers.copy()
            alt_answers["pace"] = opposite_pace
            alt_key = context_key(alt_answers)

            await weights_repo.add_weight_delta(user_id, alt_key, 1)
            weight_changes[alt_key] = weight_changes.get(alt_key, 0) + 1

        elif reason == "tooheavy":
            # Boost preference for lighter content
            current_state = answers.get("state", "escape")
            lighter_state = _get_opposite_state(current_state)

            if lighter_state != current_state:
                alt_answers = answers.copy()
                alt_answers["state"] = lighter_state
                alt_key = context_key(alt_answers)

                await weights_repo.add_weight_delta(user_id, alt_key, 1)
                weight_changes[alt_key] = weight_changes.get(alt_key, 0) + 1

        elif reason == "notvibe":
            # For "not my vibe", we can't easily adjust
            # Log it for potential future analysis
            tone_bucket = context.get("tone_bucket")
            if tone_bucket:
                # Could add tone-based weight keys in future
                pass

    # Log the event
    await events_repo.log_event(
        event_name="weights_updated",
        user_id=user_id,
        rec_id=rec_id,
        payload={
            "action": action,
            "reason": reason,
            "reward": reward,
            "weight_changes": weight_changes,
            "context_key": key,
        },
    )

    return weight_changes


async def get_user_weight(
    session: AsyncSession,
    user_id: str,
    answers: dict[str, str],
) -> int:
    """Get user's weight for a specific context.

    Args:
        session: Database session
        user_id: User ID
        answers: User answers dict

    Returns:
        Weight value (default 0)
    """
    weights_repo = WeightsRepo(session)
    key = context_key(answers)
    return await weights_repo.get_weight(user_id, key)


async def get_all_user_weights(
    session: AsyncSession,
    user_id: str,
) -> dict[str, int]:
    """Get all weights for a user.

    Args:
        session: Database session
        user_id: User ID

    Returns:
        Dict of context_key -> weight
    """
    weights_repo = WeightsRepo(session)
    return await weights_repo.get_all_weights(user_id)


def calculate_weight_bonus(weight: int, multiplier: float = 0.25) -> float:
    """Calculate weight bonus for scoring.

    Applies soft capping to prevent runaway weights.

    Args:
        weight: Raw weight value
        multiplier: Base multiplier

    Returns:
        Weight bonus (capped)
    """
    # Soft cap: diminishing returns beyond +/- 10
    if abs(weight) <= 10:
        return weight * multiplier
    else:
        # Log scaling for extreme values
        import math
        sign = 1 if weight > 0 else -1
        capped = 10 + math.log(abs(weight) - 9)
        return sign * capped * multiplier

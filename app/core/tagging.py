"""Tag parsing and matching logic for recommendations."""

import json
from typing import Any, Literal

# Normalized tag keys
PACE_VALUES = ("slow", "fast")
MOOD_VALUES = ("light", "heavy", "escape")
INTENSITY_RANGE = range(1, 6)  # 1-5

# State to mood mapping
STATE_TO_MOOD: dict[str, str] = {
    "light": "light",
    "heavy": "heavy",
    "escape": "escape",
}


def parse_tags(tags_json: str | None) -> dict[str, Any] | None:
    """Safely parse tags_json into dict.

    Args:
        tags_json: JSON string of tags

    Returns:
        Parsed dict or None if invalid/empty
    """
    if not tags_json:
        return None

    try:
        tags = json.loads(tags_json)
        if not isinstance(tags, dict):
            return None
        return tags
    except (json.JSONDecodeError, TypeError):
        return None


def normalize_pace(pace: Any) -> str | None:
    """Normalize pace value.

    Args:
        pace: Raw pace value from tags

    Returns:
        "slow" or "fast", or None if invalid
    """
    if pace is None:
        return None

    pace_str = str(pace).lower().strip()

    if pace_str in ("slow", "meditative", "contemplative", "leisurely"):
        return "slow"
    elif pace_str in ("fast", "quick", "rapid", "dynamic", "intense"):
        return "fast"
    elif pace_str in ("medium", "moderate", "balanced"):
        # Treat medium as slow for matching (safer default)
        return "slow"

    return None


def normalize_mood(mood: Any) -> list[str]:
    """Normalize mood value to list.

    Args:
        mood: Raw mood value from tags (string or list)

    Returns:
        List of normalized mood values
    """
    if mood is None:
        return []

    if isinstance(mood, str):
        moods = [mood]
    elif isinstance(mood, list):
        moods = mood
    else:
        return []

    result = []
    for m in moods:
        m_str = str(m).lower().strip()
        # Map various mood descriptions to our normalized values
        if m_str in ("light", "uplifting", "fun", "cheerful", "cozy", "warm", "hopeful"):
            result.append("light")
        elif m_str in ("heavy", "dark", "intense", "dramatic", "serious", "deep", "profound"):
            result.append("heavy")
        elif m_str in ("escape", "escapist", "immersive", "adventure", "fantasy", "otherworldly"):
            result.append("escape")

    return list(set(result))  # Remove duplicates


def normalize_tone(tone: Any) -> list[str]:
    """Normalize tone value to list.

    Args:
        tone: Raw tone value from tags

    Returns:
        List of tone values
    """
    if tone is None:
        return []

    if isinstance(tone, str):
        return [tone.lower().strip()]
    elif isinstance(tone, list):
        return [str(t).lower().strip() for t in tone]

    return []


def normalize_intensity(intensity: Any) -> int | None:
    """Normalize intensity to 1-5 scale.

    Args:
        intensity: Raw intensity value

    Returns:
        Integer 1-5 or None
    """
    if intensity is None:
        return None

    try:
        val = int(intensity)
        return max(1, min(5, val))  # Clamp to 1-5
    except (ValueError, TypeError):
        return None


def match_score(
    item_tags: dict[str, Any] | None,
    answers: dict[str, str],
    require_tags: bool = False,
) -> float:
    """Calculate match score between item tags and user answers.

    Scoring:
    - +2 if pace matches
    - +2 if mood contains the user's selected state mapping
    - +0.5 bonus for tone overlap (if applicable)

    Args:
        item_tags: Parsed item tags dict
        answers: User answers dict with state, pace, format keys
        require_tags: If True, return -inf for items without tags

    Returns:
        Match score (can be negative if require_tags=True and no tags)
    """
    if item_tags is None:
        return float("-inf") if require_tags else 0.0

    score = 0.0

    # Extract user preferences
    user_state = answers.get("state", "escape")
    user_pace = answers.get("pace", "slow")

    # Pace matching (+2)
    item_pace = normalize_pace(item_tags.get("pace"))
    if item_pace and item_pace == user_pace:
        score += 2.0

    # Mood matching (+2)
    item_moods = normalize_mood(item_tags.get("mood"))
    target_mood = STATE_TO_MOOD.get(user_state, "escape")
    if target_mood in item_moods:
        score += 2.0

    # Tone bonus (+0.5 for any overlap)
    item_tones = normalize_tone(item_tags.get("tone"))
    if item_tones:
        # Define tone buckets based on mood
        if user_state == "light":
            preferred_tones = {"cozy", "warm", "heartfelt", "funny", "romantic", "sweet"}
        elif user_state == "heavy":
            preferred_tones = {"dark", "tense", "thought-provoking", "emotional", "profound"}
        else:  # escape
            preferred_tones = {"adventure", "mysterious", "fantastical", "thrilling", "epic"}

        if any(t in preferred_tones for t in item_tones):
            score += 0.5

    # Intensity consideration
    item_intensity = normalize_intensity(item_tags.get("intensity"))
    if item_intensity is not None:
        # Light state prefers lower intensity (1-2)
        # Heavy state prefers higher intensity (4-5)
        # Escape state is flexible (2-4)
        if user_state == "light" and item_intensity <= 2:
            score += 0.3
        elif user_state == "heavy" and item_intensity >= 4:
            score += 0.3
        elif user_state == "escape" and 2 <= item_intensity <= 4:
            score += 0.3

    return score


def get_tone_bucket(tags: dict[str, Any] | None, state: str) -> str:
    """Get a tone bucket label for delta explanations.

    Args:
        tags: Item tags
        state: User state

    Returns:
        Tone bucket label
    """
    if not tags:
        return "varied"

    tones = normalize_tone(tags.get("tone"))

    cozy_tones = {"cozy", "warm", "heartfelt", "romantic", "sweet"}
    dark_tones = {"dark", "tense", "thriller", "noir", "moody"}
    adventure_tones = {"adventure", "action", "thrilling", "epic"}

    if any(t in cozy_tones for t in tones):
        return "cozy/warm"
    elif any(t in dark_tones for t in tones):
        return "dark/tense"
    elif any(t in adventure_tones for t in tones):
        return "adventure"

    return "varied"


def context_key(answers: dict[str, str]) -> str:
    """Generate a context key from answers for weight tracking.

    Format: state:{state}|pace:{pace}|format:{format}

    Args:
        answers: User answers dict

    Returns:
        Context key string
    """
    state = answers.get("state", "escape")
    pace = answers.get("pace", "slow")
    fmt = answers.get("format", "movie")
    return f"state:{state}|pace:{pace}|format:{fmt}"


def context_key_partial(state: str | None = None, pace: str | None = None, fmt: str | None = None) -> str:
    """Generate a partial context key for weight lookups.

    Args:
        state: Optional state
        pace: Optional pace
        fmt: Optional format

    Returns:
        Partial context key
    """
    parts = []
    if state:
        parts.append(f"state:{state}")
    if pace:
        parts.append(f"pace:{pace}")
    if fmt:
        parts.append(f"format:{fmt}")
    return "|".join(parts)

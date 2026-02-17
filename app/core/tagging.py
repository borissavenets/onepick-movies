"""Tag parsing and matching logic for recommendations."""

import json
from dataclasses import dataclass
from typing import Any

from app.logging import get_logger

logger = get_logger(__name__)

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


# --- Hint parsing ---

# UA/EN keyword -> answer overrides and search keywords
# Each entry: (keywords_set, overrides_dict, search_terms)
HINT_GENRE_MAP: list[tuple[set[str], dict[str, str], set[str]]] = [
    # Detective / Crime
    (
        {"детектив", "detective", "кримінал", "crime", "розслідування"},
        {"state": "heavy", "pace": "slow"},
        {"dark", "mysterious", "tense"},
    ),
    # Action
    (
        {"екшн", "action", "бойовик", "бій", "стрілянина"},
        {"state": "escape", "pace": "fast"},
        {"adventure", "thrilling"},
    ),
    # Comedy
    (
        {"комедія", "comedy", "смішне", "смішний", "веселе", "веселий"},
        {"state": "light", "pace": "fast"},
        {"funny", "warm"},
    ),
    # Drama
    (
        {"драма", "drama", "драматичне", "драматичний"},
        {"state": "heavy", "pace": "slow"},
        {"melancholy", "emotional"},
    ),
    # Horror / Thriller
    (
        {"хорор", "horror", "жахи", "страшне", "трилер", "thriller"},
        {"state": "heavy", "pace": "fast"},
        {"dark", "tense"},
    ),
    # Romance
    (
        {"романтика", "romance", "романтичне", "кохання", "love"},
        {"state": "light", "pace": "slow"},
        {"warm", "romantic"},
    ),
    # Fantasy / Sci-fi
    (
        {"фантастика", "fantasy", "фентезі", "sci-fi", "наукова фантастика", "космос"},
        {"state": "escape"},
        {"weird", "adventure"},
    ),
    # Animation
    (
        {"мультфільм", "мультик", "анімація", "animation", "anime", "аніме"},
        {"state": "light"},
        {"cozy", "warm"},
    ),
    # Korean
    (
        {"корейське", "корейська", "корейський", "korean", "k-drama", "кдрама", "дорама"},
        {},
        set(),
    ),
    # Chinese
    (
        {"китайське", "китайська", "китайський", "chinese", "china"},
        {},
        set(),
    ),
    # Documentary
    (
        {"документальне", "документалка", "documentary"},
        {"state": "heavy", "pace": "slow"},
        {"thought-provoking"},
    ),
    # Slow / contemplative
    (
        {"повільне", "повільний", "спокійне", "вдумливе"},
        {"pace": "slow"},
        set(),
    ),
    # Dynamic / fast
    (
        {"динамічне", "динамічний", "швидке", "драйв", "адреналін"},
        {"pace": "fast"},
        set(),
    ),
]

# Pace keywords (explicit override)
HINT_PACE_KEYWORDS: dict[str, str] = {
    "повільне": "slow", "повільний": "slow", "спокійне": "slow",
    "вдумливе": "slow", "неквапливе": "slow",
    "динамічне": "fast", "динамічний": "fast", "швидке": "fast",
    "швидкий": "fast", "драйв": "fast", "екшн": "fast",
}


@dataclass
class HintResult:
    """Parsed hint data."""

    overrides: dict[str, str]  # state/pace/format overrides
    tone_keywords: set[str]  # tone tags to boost
    search_words: list[str]  # raw UA words for title matching
    llm_keywords: list[str]  # LLM keywords for overview/genres/credits


def parse_hint(hint: str | None) -> HintResult:
    """Parse free-text hint into overrides and search keywords.

    Args:
        hint: User's free-text hint (UA or EN)

    Returns:
        HintResult with overrides, tone keywords, and search words
    """
    if not hint or not hint.strip():
        return HintResult(overrides={}, tone_keywords=set(), search_words=[], llm_keywords=[])

    text = hint.lower().strip()
    words = text.split()

    overrides: dict[str, str] = {}
    tone_keywords: set[str] = set()

    # Format override from hint text
    series_words = {"серіал", "серіали", "series", "show", "шоу", "дорама"}
    movie_words = {"фільм", "фільми", "movie", "кіно"}
    if any(w in series_words for w in words):
        overrides["format"] = "series"
    elif any(w in movie_words for w in words):
        overrides["format"] = "movie"

    # Match against genre map
    for keywords, genre_overrides, tones in HINT_GENRE_MAP:
        if any(w in keywords for w in words) or any(kw in text for kw in keywords if " " in kw):
            overrides.update(genre_overrides)
            tone_keywords.update(tones)

    # Extract meaningful search words (skip short/common words)
    stop_words = {
        "щось", "як", "на", "з", "із", "та", "і", "або", "чи",
        "схоже", "подібне", "типу", "класний", "класне", "класна",
        "гарний", "гарне", "гарна", "крутий", "круте", "крута",
        "хороший", "хороше", "хороша", "цікавий", "цікаве", "цікава",
        "something", "like", "similar", "good", "cool", "nice", "great",
        "want", "хочу", "хочеться", "давай", "може", "можливо",
        "про", "about", "with",
        "фільм", "серіал", "movie", "series", "show",
    }
    search_words = [w for w in words if len(w) >= 3 and w not in stop_words]

    return HintResult(
        overrides=overrides, tone_keywords=tone_keywords,
        search_words=search_words, llm_keywords=[],
    )


async def translate_hint_keywords(hint_text: str) -> list[str]:
    """Translate UA hint to English keywords via LLM.

    On any error returns [] silently (fallback to UA-only matching).
    """
    if not hint_text or not hint_text.strip():
        return []

    try:
        from app.llm.llm_adapter import LLMDisabledError, OpenAIError, generate_text

        response = await generate_text(
            system_prompt=(
                "Extract search keywords from a Ukrainian movie/series request. "
                "Return keywords in BOTH Ukrainian and English, comma-separated. "
                "Include: actor/director names, genres, themes, settings. "
                "Return ONLY comma-separated keywords, nothing else."
            ),
            user_prompt=hint_text.strip(),
            max_tokens=100,
            temperature=0.2,
        )
        keywords = [kw.strip().lower() for kw in response.split(",") if kw.strip()]
        return keywords

    except (LLMDisabledError, OpenAIError) as e:
        logger.debug(f"LLM hint translation skipped: {e}")
        return []
    except Exception as e:
        logger.warning(f"LLM hint translation failed: {e}")
        return []


def hint_match_score(
    item_title: str,
    item_tags: dict[str, Any] | None,
    hint_result: HintResult,
    overview: str | None = None,
    genres_json: str | None = None,
    credits_json: str | None = None,
) -> float:
    """Calculate bonus score for hint keyword matches.

    Args:
        item_title: Item title for keyword matching
        item_tags: Parsed item tags
        hint_result: Parsed hint data
        overview: Item overview/description text
        genres_json: JSON string of genre names
        credits_json: JSON string with director and actors

    Returns:
        Bonus score (0.0 to 8.0)
    """
    all_words = hint_result.search_words + hint_result.llm_keywords
    if not all_words and not hint_result.tone_keywords:
        return 0.0

    score = 0.0
    title_lower = item_title.lower()

    # Title keyword match (+3.0 per match) - UA words + LLM keywords
    for word in all_words:
        if word in title_lower:
            score += 3.0

    # Tone keyword match against item tags (+1.5 per match)
    if item_tags and hint_result.tone_keywords:
        item_tones = normalize_tone(item_tags.get("tone"))
        for tone in hint_result.tone_keywords:
            if tone in item_tones:
                score += 1.5

    # Below: only LLM keywords (proper word forms for both UA and EN)
    llm_words = hint_result.llm_keywords
    if not llm_words:
        return min(score, 8.0)

    # Overview keyword match (+1.0 per word)
    if overview:
        overview_lower = overview.lower()
        for word in llm_words:
            if word in overview_lower:
                score += 1.0

    # Genre keyword match (+2.0 per word)
    if genres_json:
        try:
            genres_lower = genres_json.lower()
            for word in llm_words:
                if word in genres_lower:
                    score += 2.0
        except (json.JSONDecodeError, TypeError):
            pass

    # Credits keyword match (+3.0 per word)
    if credits_json:
        try:
            credits_lower = credits_json.lower()
            for word in llm_words:
                if word in credits_lower:
                    score += 3.0
        except (json.JSONDecodeError, TypeError):
            pass

    return min(score, 8.0)

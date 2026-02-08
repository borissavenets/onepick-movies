"""Heuristic tag generation for TMDB items."""

from app.storage.json_utils import safe_json_dumps

# Genre mappings for TMDB genre IDs and names
# TMDB genre IDs: https://developers.themoviedb.org/3/genres/get-movie-list

# Pace mapping: fast-paced genres
FAST_PACE_GENRES = {
    "action", "thriller", "horror", "crime", "adventure",
    28, 53, 27, 80, 12,  # TMDB IDs
}

# Mood mappings
LIGHT_MOOD_GENRES = {
    "comedy", "animation", "family", "music", "romance",
    35, 16, 10751, 10402, 10749,
}

HEAVY_MOOD_GENRES = {
    "drama", "war", "history", "documentary",
    18, 10752, 36, 99,
}

ESCAPE_MOOD_GENRES = {
    "fantasy", "science fiction", "adventure", "animation",
    14, 878, 12, 16,
}

# Tone mappings (genre -> possible tones)
TONE_MAPPINGS = {
    # Cozy/Warm
    "family": ["cozy", "warm"],
    "animation": ["cozy", "warm"],
    "romance": ["warm"],
    10751: ["cozy", "warm"],
    16: ["cozy", "warm"],
    10749: ["warm"],

    # Dark/Tense
    "horror": ["dark", "tense"],
    "thriller": ["dark", "tense"],
    "crime": ["dark"],
    "mystery": ["dark", "mysterious"],
    27: ["dark", "tense"],
    53: ["dark", "tense"],
    80: ["dark"],
    9648: ["dark", "mysterious"],

    # Funny
    "comedy": ["funny"],
    35: ["funny"],

    # Uplifting
    "music": ["uplifting"],
    10402: ["uplifting"],

    # Melancholy
    "drama": ["melancholy"],
    18: ["melancholy"],

    # Mysterious
    "mystery": ["mysterious"],
    9648: ["mysterious"],

    # Weird
    "science fiction": ["weird"],
    878: ["weird"],
}

# Keywords in overview that suggest tones
OVERVIEW_TONE_KEYWORDS = {
    "dark": ["dark", "sinister", "evil", "death", "murder", "killer"],
    "tense": ["suspense", "tension", "thriller", "chase", "escape", "danger"],
    "funny": ["hilarious", "comedy", "laugh", "funny", "humor"],
    "warm": ["heartwarming", "touching", "family", "friendship", "love"],
    "mysterious": ["mystery", "secret", "hidden", "enigma", "puzzle"],
    "uplifting": ["inspiring", "triumph", "overcome", "hope", "dream"],
    "melancholy": ["loss", "grief", "tragedy", "farewell", "memories"],
}


def _normalize_genre(genre) -> str | int:
    """Normalize genre to lowercase string or int ID."""
    if isinstance(genre, int):
        return genre
    if isinstance(genre, str):
        return genre.lower().strip()
    if isinstance(genre, dict):
        # TMDB format: {"id": 28, "name": "Action"}
        return genre.get("id") or genre.get("name", "").lower()
    return ""


def _get_pace(genres: list) -> str:
    """Determine pace from genres."""
    normalized = [_normalize_genre(g) for g in genres]

    for g in normalized:
        if g in FAST_PACE_GENRES:
            return "fast"

    return "slow"


def _get_mood(genres: list) -> str:
    """Determine mood from genres."""
    normalized = [_normalize_genre(g) for g in genres]

    # Check in order of priority
    for g in normalized:
        if g in ESCAPE_MOOD_GENRES:
            return "escape"

    for g in normalized:
        if g in LIGHT_MOOD_GENRES:
            return "light"

    for g in normalized:
        if g in HEAVY_MOOD_GENRES:
            return "heavy"

    return "escape"  # Default


def _get_tones(genres: list, overview: str | None) -> list[str]:
    """Determine tones from genres and overview."""
    tones = set()
    normalized = [_normalize_genre(g) for g in genres]

    # Get tones from genres
    for g in normalized:
        if g in TONE_MAPPINGS:
            for tone in TONE_MAPPINGS[g]:
                tones.add(tone)

    # Check overview for tone keywords
    if overview:
        overview_lower = overview.lower()
        for tone, keywords in OVERVIEW_TONE_KEYWORDS.items():
            if any(kw in overview_lower for kw in keywords):
                tones.add(tone)

    # Limit to 2 tones, prioritize variety
    tone_list = list(tones)
    if len(tone_list) > 2:
        # Prefer one "feeling" tone and one "atmosphere" tone
        feeling_tones = {"warm", "funny", "uplifting", "melancholy"}
        atmosphere_tones = {"dark", "tense", "mysterious", "cozy", "weird"}

        result = []
        for t in tone_list:
            if t in feeling_tones and len(result) < 1:
                result.append(t)
        for t in tone_list:
            if t in atmosphere_tones and len(result) < 2:
                result.append(t)
        if len(result) < 2:
            for t in tone_list:
                if t not in result and len(result) < 2:
                    result.append(t)
        return result

    return tone_list if tone_list else ["warm"]


def _get_intensity(genres: list, vote_average: float | None = None) -> int:
    """Determine intensity 1-5 from genres and rating."""
    normalized = [_normalize_genre(g) for g in genres]

    # High intensity genres
    high_intensity = {"horror", "thriller", "war", "action", 27, 53, 10752, 28}
    # Low intensity genres
    low_intensity = {"animation", "family", "comedy", "romance", 16, 10751, 35, 10749}

    base = 3

    for g in normalized:
        if g in high_intensity:
            base = max(base, 4)
        elif g in low_intensity:
            base = min(base, 2)

    # Adjust by vote average if available
    if vote_average is not None:
        if vote_average >= 8.0:
            base = min(base + 1, 5)
        elif vote_average < 6.0:
            base = max(base - 1, 1)

    return base


def heuristic_tags(
    genres: list,
    overview: str | None = None,
    vote_average: float | None = None,
) -> str:
    """Generate heuristic tags_json from TMDB data.

    Args:
        genres: List of genres (strings, IDs, or dicts with id/name)
        overview: Movie/series description text
        vote_average: TMDB vote average (0-10)

    Returns:
        JSON string with tags: pace, mood, tone, intensity
    """
    if not genres:
        genres = []

    tags = {
        "pace": [_get_pace(genres)],
        "mood": [_get_mood(genres)],
        "tone": _get_tones(genres, overview),
        "intensity": _get_intensity(genres, vote_average),
    }

    return safe_json_dumps(tags)

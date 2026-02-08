"""Core module containing recommendation engine and domain types."""

from app.core.contracts import (
    ContentItem,
    ContentType,
    FeedbackAction,
    Format,
    MissReason,
    Pace,
    RecommendationResult,
    Recommender,
    UserAnswers,
    UserFeedback,
    UserState,
)
from app.core.learning import update_weights
from app.core.recommender import get_recommendation
from app.core.rationale import (
    generate_rationale,
    generate_when_to_watch,
    generate_delta_explainer,
    validate_rationale,
    MAX_RATIONALE_LENGTH,
    SPOILER_KEYWORDS,
)
from app.core.tagging import (
    context_key,
    match_score,
    parse_tags,
    normalize_pace,
    normalize_mood,
)
from app.core.anti_repeat import get_excluded_item_ids

__all__ = [
    # Contracts/Types
    "ContentItem",
    "ContentType",
    "FeedbackAction",
    "Format",
    "MissReason",
    "Pace",
    "RecommendationResult",
    "Recommender",
    "UserAnswers",
    "UserFeedback",
    "UserState",
    # Main functions
    "get_recommendation",
    "update_weights",
    # Rationale
    "generate_rationale",
    "generate_when_to_watch",
    "generate_delta_explainer",
    "validate_rationale",
    "MAX_RATIONALE_LENGTH",
    "SPOILER_KEYWORDS",
    # Tagging
    "context_key",
    "match_score",
    "parse_tags",
    "normalize_pace",
    "normalize_mood",
    # Anti-repeat
    "get_excluded_item_ids",
]

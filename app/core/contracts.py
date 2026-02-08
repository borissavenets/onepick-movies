"""Domain contracts and type definitions."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, Protocol


class ContentType(str, Enum):
    """Types of content that can be curated."""

    MOVIE = "movie"
    SERIES = "series"
    DOCUMENTARY = "documentary"
    SHORT = "short"


class FeedbackAction(str, Enum):
    """Types of user feedback actions."""

    HIT = "hit"
    MISS = "miss"
    ANOTHER = "another"
    FAVORITE = "favorite"
    SHARE = "share"
    SILENT_DROP = "silent_drop"


class MissReason(str, Enum):
    """Reasons for missing recommendation."""

    TOO_SLOW = "tooslow"
    TOO_HEAVY = "tooheavy"
    NOT_MY_VIBE = "notvibe"


class UserState(str, Enum):
    """User emotional state options."""

    LIGHT = "light"
    HEAVY = "heavy"
    ESCAPE = "escape"


class Pace(str, Enum):
    """Content pace preferences."""

    SLOW = "slow"
    FAST = "fast"


class Format(str, Enum):
    """Content format preferences."""

    MOVIE = "movie"
    SERIES = "series"


@dataclass
class UserAnswers:
    """User's flow answers."""

    state: str
    pace: str
    format: str

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary."""
        return {
            "state": self.state,
            "pace": self.pace,
            "format": self.format,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "UserAnswers":
        """Create from dictionary."""
        return cls(
            state=data.get("state", "escape"),
            pace=data.get("pace", "slow"),
            format=data.get("format", "movie"),
        )


@dataclass
class RecommendationResult:
    """Result from recommendation engine."""

    rec_id: str
    item_id: str
    title: str
    rationale: str
    when_to_watch: str


@dataclass
class ContentItem:
    """Represents a curated content item."""

    id: str
    title: str
    description: str
    content_type: ContentType
    source_url: str | None = None
    image_url: str | None = None
    metadata: dict | None = None
    created_at: datetime | None = None


@dataclass
class UserFeedback:
    """Represents user feedback on a content item."""

    user_id: str
    rec_id: str
    action: FeedbackAction
    reason: str | None = None
    created_at: datetime | None = None


class Recommender(Protocol):
    """Protocol for recommendation engine."""

    async def get_recommendation(
        self,
        user_id: str,
        answers: dict[str, str],
        mode: Literal["normal", "another", "miss_recover"] = "normal",
        exclude_item_ids: set[str] | None = None,
        last_context: dict | None = None,
    ) -> RecommendationResult | None:
        """Get a recommendation based on user answers.

        Args:
            user_id: User ID
            answers: User answers dict with state, pace, format keys
            mode: Recommendation mode
            exclude_item_ids: Item IDs to exclude
            last_context: Previous recommendation context for "another" mode

        Returns:
            RecommendationResult or None if unavailable
        """
        ...

    async def update_weights(
        self,
        user_id: str,
        rec_id: str,
        action: str,
        reason: str | None = None,
    ) -> dict[str, int]:
        """Update user weights based on feedback.

        Args:
            user_id: User ID
            rec_id: Recommendation ID
            action: Feedback action (hit, miss, another, etc.)
            reason: Optional miss reason

        Returns:
            Dict of weight changes applied
        """
        ...


class ContentRepository(Protocol):
    """Protocol for content storage operations."""

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Retrieve a content item by ID."""
        ...

    async def get_random_item(self, exclude_ids: list[str] | None = None) -> ContentItem | None:
        """Get a random content item, optionally excluding certain IDs."""
        ...

    async def save_item(self, item: ContentItem) -> None:
        """Save a content item."""
        ...


class FeedbackRepository(Protocol):
    """Protocol for feedback storage operations."""

    async def save_feedback(self, feedback: UserFeedback) -> None:
        """Save user feedback."""
        ...

    async def get_user_feedback(self, user_id: str) -> list[UserFeedback]:
        """Get all feedback from a user."""
        ...

    async def get_item_feedback(self, item_id: str) -> list[UserFeedback]:
        """Get all feedback for an item."""
        ...

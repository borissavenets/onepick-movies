"""Storage module for database operations."""

from app.storage.db import Base, close_engine, get_engine, get_session_factory
from app.storage.heuristics import heuristic_tags
from app.storage.json_utils import safe_json_dumps, safe_json_loads
from app.storage.models import (
    ABWinner,
    Alert,
    DailyMetric,
    Event,
    Favorite,
    Feedback,
    Item,
    Post,
    PostMetric,
    Recommendation,
    User,
    UserWeight,
)
from app.storage.repo_ab_winners import ABWinnersRepo
from app.storage.repo_alerts import AlertsRepo
from app.storage.repo_daily_metrics import DailyMetricsRepo
from app.storage.repo_events import EventsRepo
from app.storage.repo_favorites import FavoritesRepo
from app.storage.repo_feedback import FeedbackRepo
from app.storage.repo_items import ItemsRepo
from app.storage.repo_metrics import MetricsRepo
from app.storage.repo_posts import PostsRepo
from app.storage.repo_recs import RecsRepo
from app.storage.repo_users import UsersRepo
from app.storage.repo_weights import WeightsRepo

__all__ = [
    # Database
    "Base",
    "get_engine",
    "get_session_factory",
    "close_engine",
    # JSON utilities
    "safe_json_dumps",
    "safe_json_loads",
    # Heuristics
    "heuristic_tags",
    # Models
    "User",
    "UserWeight",
    "Item",
    "Recommendation",
    "Feedback",
    "Favorite",
    "Post",
    "PostMetric",
    "ABWinner",
    "Event",
    "DailyMetric",
    "Alert",
    # Repositories
    "UsersRepo",
    "WeightsRepo",
    "ItemsRepo",
    "RecsRepo",
    "FeedbackRepo",
    "FavoritesRepo",
    "PostsRepo",
    "MetricsRepo",
    "ABWinnersRepo",
    "EventsRepo",
    "DailyMetricsRepo",
    "AlertsRepo",
]

"""SQLAlchemy ORM models for FramePick."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base


class User(Base):
    """User profile and activity tracking."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    weights: Mapped[list["UserWeight"]] = relationship(
        "UserWeight", back_populates="user", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        "Recommendation", back_populates="user"
    )
    feedback: Mapped[list["Feedback"]] = relationship("Feedback", back_populates="user")
    favorites: Mapped[list["Favorite"]] = relationship(
        "Favorite", back_populates="user", cascade="all, delete-orphan"
    )
    dismissed: Mapped[list["DismissedItem"]] = relationship(
        "DismissedItem", back_populates="user", cascade="all, delete-orphan"
    )


class UserWeight(Base):
    """User preference weights for personalization."""

    __tablename__ = "user_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="weights")

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_weights_user_key"),)


class Item(Base):
    """Content items (movies, series)."""

    __tablename__ = "items"

    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    base_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    curated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # TMDB-ready fields
    source: Mapped[str] = mapped_column(String, nullable=False, default="curated")
    source_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tag_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    tag_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    poster_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vote_average: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Detail fields (populated from TMDB)
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    genres_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credits_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    recommendations: Mapped[list["Recommendation"]] = relationship(
        "Recommendation", back_populates="item"
    )
    favorites: Mapped[list["Favorite"]] = relationship("Favorite", back_populates="item")

    __table_args__ = (
        CheckConstraint("type IN ('movie', 'series')", name="ck_items_type"),
        # Index on source+source_id for lookups (non-unique to allow NULL source_id)
        Index("ix_items_source_source_id", "source", "source_id"),
    )


class Recommendation(Base):
    """Recommendation records linking users to items."""

    __tablename__ = "recommendations"

    rec_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(
        String, ForeignKey("items.item_id"), nullable=False
    )
    context_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="recommendations")
    item: Mapped["Item"] = relationship("Item", back_populates="recommendations")
    feedback: Mapped[list["Feedback"]] = relationship(
        "Feedback", back_populates="recommendation"
    )

    __table_args__ = (Index("ix_recommendations_user_created", "user_id", "created_at"),)


class Feedback(Base):
    """User feedback on recommendations."""

    __tablename__ = "feedback"

    feedback_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rec_id: Mapped[str] = mapped_column(
        String, ForeignKey("recommendations.rec_id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    recommendation: Mapped["Recommendation"] = relationship(
        "Recommendation", back_populates="feedback"
    )
    user: Mapped["User"] = relationship("User", back_populates="feedback")

    __table_args__ = (
        CheckConstraint(
            "action IN ('hit', 'miss', 'another', 'favorite', 'share', 'silent_drop', 'dismissed')",
            name="ck_feedback_action",
        ),
        Index("ix_feedback_user_created", "user_id", "created_at"),
        Index("ix_feedback_rec_id", "rec_id"),
    )


class Favorite(Base):
    """User favorites."""

    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(
        String, ForeignKey("items.item_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="favorites")
    item: Mapped["Item"] = relationship("Item", back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_favorites_user_item"),
    )


class DismissedItem(Base):
    """Items dismissed by user ('already watched') — permanently excluded from recommendations."""

    __tablename__ = "dismissed_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(
        String, ForeignKey("items.item_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="dismissed")
    item: Mapped["Item"] = relationship("Item")

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_dismissed_user_item"),
    )


class Post(Base):
    """Channel posts with A/B variant tracking."""

    __tablename__ = "posts"

    post_id: Mapped[str] = mapped_column(String, primary_key=True)
    format_id: Mapped[str] = mapped_column(String, nullable=False)
    hypothesis_id: Mapped[str] = mapped_column(String, nullable=False)
    variant_id: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    metrics: Mapped[list["PostMetric"]] = relationship(
        "PostMetric", back_populates="post", cascade="all, delete-orphan"
    )


class PostMetric(Base):
    """Metrics snapshots for posts."""

    __tablename__ = "post_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(
        String, ForeignKey("posts.post_id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    forwards: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bot_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsub_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    post: Mapped["Post"] = relationship("Post", back_populates="metrics")

    __table_args__ = (Index("ix_post_metrics_post_captured", "post_id", "captured_at"),)


class ABWinner(Base):
    """A/B test winner locks."""

    __tablename__ = "ab_winners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hypothesis_id: Mapped[str] = mapped_column(String, nullable=False)
    winner_variant_id: Mapped[str] = mapped_column(String, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (Index("ix_ab_winners_hypothesis_ends", "hypothesis_id", "ends_at"),)


class Event(Base):
    """Event logging for analytics."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_name: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rec_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    post_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_events_name_created", "event_name", "created_at"),
        Index("ix_events_user_created", "user_id", "created_at"),
    )


class DailyMetric(Base):
    """Daily aggregated metrics for observability."""

    __tablename__ = "daily_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD
    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("date", "metric_name", name="uq_daily_metrics_date_name"),
        Index("ix_daily_metrics_name_date", "metric_name", "date"),
    )


class Alert(Base):
    """Lightweight alerts for SLO violations and anomalies."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False, default="warning")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_alerts_severity",
        ),
        Index("ix_alerts_type_created", "alert_type", "created_at"),
    )

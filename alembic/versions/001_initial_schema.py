"""Initial schema with all MVP tables.

Revision ID: 001_initial_schema
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("reset_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # User weights table
    op.create_table(
        "user_weights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_user_weights_user_key"),
    )

    # Items table
    op.create_table(
        "items",
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("tags_json", sa.Text(), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("base_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("curated", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("type IN ('movie', 'series')", name="ck_items_type"),
        sa.PrimaryKeyConstraint("item_id"),
    )

    # Recommendations table
    op.create_table(
        "recommendations",
        sa.Column("rec_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.item_id"]),
        sa.PrimaryKeyConstraint("rec_id"),
    )
    op.create_index(
        "ix_recommendations_user_created",
        "recommendations",
        ["user_id", "created_at"],
    )

    # Feedback table
    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rec_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "action IN ('hit', 'miss', 'another', 'favorite', 'share', 'silent_drop')",
            name="ck_feedback_action",
        ),
        sa.ForeignKeyConstraint(["rec_id"], ["recommendations.rec_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("feedback_id"),
    )
    op.create_index("ix_feedback_user_created", "feedback", ["user_id", "created_at"])
    op.create_index("ix_feedback_rec_id", "feedback", ["rec_id"])

    # Favorites table
    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.item_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "item_id", name="uq_favorites_user_item"),
    )

    # Posts table
    op.create_table(
        "posts",
        sa.Column("post_id", sa.String(), nullable=False),
        sa.Column("format_id", sa.String(), nullable=False),
        sa.Column("hypothesis_id", sa.String(), nullable=False),
        sa.Column("variant_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("post_id"),
    )

    # Post metrics table
    op.create_table(
        "post_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.String(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reactions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forwards", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bot_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unsub_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.post_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_post_metrics_post_captured",
        "post_metrics",
        ["post_id", "captured_at"],
    )

    # A/B winners table
    op.create_table(
        "ab_winners",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hypothesis_id", sa.String(), nullable=False),
        sa.Column("winner_variant_id", sa.String(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ab_winners_hypothesis_ends",
        "ab_winners",
        ["hypothesis_id", "ends_at"],
    )

    # Events table
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_name", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("rec_id", sa.String(), nullable=True),
        sa.Column("post_id", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_name_created", "events", ["event_name", "created_at"])
    op.create_index("ix_events_user_created", "events", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("ab_winners")
    op.drop_table("post_metrics")
    op.drop_table("posts")
    op.drop_table("favorites")
    op.drop_table("feedback")
    op.drop_table("recommendations")
    op.drop_table("items")
    op.drop_table("user_weights")
    op.drop_table("users")

"""Add TMDB-ready fields to items table.

Revision ID: 002_add_tmdb_fields
Revises: 001_initial_schema
Create Date: 2025-01-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_add_tmdb_fields"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to items table
    op.add_column(
        "items",
        sa.Column("source", sa.String(), nullable=False, server_default="curated"),
    )
    op.add_column(
        "items",
        sa.Column("source_id", sa.String(), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column("tag_status", sa.String(), nullable=False, server_default="pending"),
    )
    op.add_column(
        "items",
        sa.Column("tag_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "items",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # Update existing rows: set updated_at = created_at, tag_status = 'tagged' for curated
    op.execute(
        "UPDATE items SET updated_at = created_at, tag_status = 'tagged' WHERE source = 'curated'"
    )

    # Make updated_at NOT NULL after backfill
    # SQLite doesn't support ALTER COLUMN, so we use batch mode
    with op.batch_alter_table("items") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False,
        )

    # Create index on (source, source_id) for lookups
    # Note: Uniqueness is enforced at application level via item_id format
    op.create_index(
        "ix_items_source_source_id",
        "items",
        ["source", "source_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop index
    op.drop_index("ix_items_source_source_id", table_name="items")

    # Remove columns (using batch mode for SQLite)
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("tag_version")
        batch_op.drop_column("tag_status")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source")

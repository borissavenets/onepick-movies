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


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_column("items", "source"):
        op.add_column(
            "items",
            sa.Column("source", sa.String(), nullable=False, server_default="curated"),
        )
    if not _has_column("items", "source_id"):
        op.add_column(
            "items",
            sa.Column("source_id", sa.String(), nullable=True),
        )
    if not _has_column("items", "tag_status"):
        op.add_column(
            "items",
            sa.Column("tag_status", sa.String(), nullable=False, server_default="pending"),
        )
    if not _has_column("items", "tag_version"):
        op.add_column(
            "items",
            sa.Column("tag_version", sa.Integer(), nullable=False, server_default="1"),
        )
    if not _has_column("items", "updated_at"):
        op.add_column(
            "items",
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    if not _has_column("items", "poster_url"):
        op.add_column(
            "items",
            sa.Column("poster_url", sa.Text(), nullable=True),
        )
    if not _has_column("items", "vote_average"):
        op.add_column(
            "items",
            sa.Column("vote_average", sa.Float(), nullable=True),
        )

    # Backfill existing rows
    op.execute(
        "UPDATE items SET updated_at = created_at, tag_status = 'tagged' "
        "WHERE source = 'curated' AND updated_at IS NULL"
    )

    # Make updated_at NOT NULL (skip if already NOT NULL to avoid table rebuild)
    conn = op.get_bind()
    insp = sa.inspect(conn)
    for col in insp.get_columns("items"):
        if col["name"] == "updated_at" and col["nullable"] is False:
            break
    else:
        with op.batch_alter_table("items") as batch_op:
            batch_op.alter_column(
                "updated_at",
                existing_type=sa.DateTime(),
                nullable=False,
            )

    # Create index (ignore if exists)
    try:
        op.create_index(
            "ix_items_source_source_id",
            "items",
            ["source", "source_id"],
            unique=False,
        )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_index("ix_items_source_source_id", table_name="items")

    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("tag_version")
        batch_op.drop_column("tag_status")
        batch_op.drop_column("source_id")
        batch_op.drop_column("source")

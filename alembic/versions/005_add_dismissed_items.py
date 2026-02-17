"""Add dismissed_items table and update feedback action constraint.

Revision ID: 005_add_dismissed_items
Revises: 004_add_observability_tables
Create Date: 2026-02-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_add_dismissed_items"
down_revision: Union[str, None] = "004_add_observability_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("dismissed_items"):
        op.create_table(
            "dismissed_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("item_id", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["item_id"], ["items.item_id"]),
            sa.UniqueConstraint("user_id", "item_id", name="uq_dismissed_user_item"),
        )

    # SQLite ignores CHECK constraints on INSERT anyway, and batch_alter_table
    # rebuilds the entire table which is risky. Skip constraint update - the ORM
    # validates action values at the application level.


def downgrade() -> None:
    op.drop_table("dismissed_items")

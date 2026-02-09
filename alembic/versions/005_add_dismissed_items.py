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


def upgrade() -> None:
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

    # SQLite doesn't support ALTER CONSTRAINT, so we recreate the check
    # constraint by creating a new table. However, SQLite also ignores
    # CHECK constraints on ALTER, so for SQLite we rely on the ORM-level
    # constraint. The new action value 'dismissed' will work because
    # SQLite CHECK constraints from CREATE TABLE are already in place
    # and we handle this via batch mode.
    with op.batch_alter_table("feedback") as batch_op:
        batch_op.drop_constraint("ck_feedback_action", type_="check")
        batch_op.create_check_constraint(
            "ck_feedback_action",
            "action IN ('hit', 'miss', 'another', 'favorite', 'share', 'silent_drop', 'dismissed')",
        )


def downgrade() -> None:
    with op.batch_alter_table("feedback") as batch_op:
        batch_op.drop_constraint("ck_feedback_action", type_="check")
        batch_op.create_check_constraint(
            "ck_feedback_action",
            "action IN ('hit', 'miss', 'another', 'favorite', 'share', 'silent_drop')",
        )

    op.drop_table("dismissed_items")

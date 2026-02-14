"""Add overview, genres_json, credits_json to items table.

Revision ID: 006_add_item_details
Revises: 005_add_dismissed_items
Create Date: 2026-02-14 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "006_add_item_details"
down_revision: Union[str, None] = "005_add_dismissed_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("overview", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("genres_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("credits_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("credits_json")
        batch_op.drop_column("genres_json")
        batch_op.drop_column("overview")

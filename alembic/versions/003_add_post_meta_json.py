"""Add meta_json column to posts table.

Revision ID: 003_add_post_meta_json
Revises: 002_add_tmdb_fields
Create Date: 2025-01-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_add_post_meta_json"
down_revision: Union[str, None] = "002_add_tmdb_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    with op.batch_alter_table("posts") as batch_op:
        batch_op.drop_column("meta_json")

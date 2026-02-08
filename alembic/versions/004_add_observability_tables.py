"""Add daily_metrics and alerts tables for observability.

Revision ID: 004_add_observability_tables
Revises: 003_add_post_meta_json
Create Date: 2026-02-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_add_observability_tables"
down_revision: Union[str, None] = "003_add_post_meta_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.String(), nullable=False),
        sa.Column("metric_name", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "metric_name", name="uq_daily_metrics_date_name"),
    )
    op.create_index(
        "ix_daily_metrics_name_date", "daily_metrics", ["metric_name", "date"]
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_type", sa.String(), nullable=False),
        sa.Column(
            "severity", sa.String(), nullable=False, server_default="warning"
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_alerts_severity",
        ),
    )
    op.create_index("ix_alerts_type_created", "alerts", ["alert_type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_alerts_type_created", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_daily_metrics_name_date", table_name="daily_metrics")
    op.drop_table("daily_metrics")

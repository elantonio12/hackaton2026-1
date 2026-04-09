"""metric snapshots

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
        sa.Column("total_containers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_containers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_fill_level", sa.Float(), nullable=False, server_default="0"),
        sa.Column("predicted_full_24h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fleet_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fleet_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_routes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("optimized_km", sa.Float(), nullable=False, server_default="0"),
        sa.Column("saved_km", sa.Float(), nullable=False, server_default="0"),
        sa.Column("distance_reduction_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fuel_saved_liters", sa.Float(), nullable=False, server_default="0"),
        sa.Column("co2_avoided_kg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fuel_cost_saved_mxn", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("metric_snapshots")

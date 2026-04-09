"""trucks and routes

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trucks",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("zone", sa.String(50), index=True, nullable=False),
        sa.Column("capacity_m3", sa.Float(), nullable=False, server_default="12.0"),
        sa.Column("current_load_m3", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("depot_lat", sa.Float(), nullable=False),
        sa.Column("depot_lon", sa.Float(), nullable=False),
        sa.Column("current_lat", sa.Float(), nullable=False),
        sa.Column("current_lon", sa.Float(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="idle", index=True),
        sa.Column("current_route_id", sa.Integer(), nullable=True),
        sa.Column("assigned_user_sub", sa.String(255), nullable=True, index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("truck_id", sa.String(50), index=True, nullable=False),
        sa.Column("stops", sa.JSON(), nullable=False),
        sa.Column("polyline_geojson", sa.JSON(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("duration_min", sa.Float(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active", index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("routes")
    op.drop_table("trucks")

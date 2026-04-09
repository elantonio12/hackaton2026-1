"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("sub", sa.String(255), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("picture", sa.String(512), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="citizen"),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "sensors",
        sa.Column("sensor_id", sa.String(100), primary_key=True),
        sa.Column("container_id", sa.String(100), index=True, nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("zone", sa.String(50), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(50), nullable=False, server_default="activo"),
    )

    op.create_table(
        "container_readings",
        sa.Column("container_id", sa.String(100), primary_key=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("fill_level", sa.Float(), nullable=False),
        sa.Column("zone", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.String(50), nullable=False),
    )

    op.create_table(
        "citizen_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("zone", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "collectors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("empleado_id", sa.String(100), nullable=False),
        sa.Column("zona", sa.String(50), nullable=False),
        sa.Column("camion_id", sa.String(100), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("telefono", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "problem_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("container_id", sa.String(100), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("zone", sa.String(50), nullable=False),
        sa.Column("tipo_problema", sa.String(50), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(50), nullable=False, server_default="recibido"),
    )


def downgrade() -> None:
    op.drop_table("problem_reports")
    op.drop_table("collectors")
    op.drop_table("citizen_reports")
    op.drop_table("container_readings")
    op.drop_table("sensors")
    op.drop_table("users")

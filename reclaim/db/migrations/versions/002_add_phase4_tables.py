"""Add Phase 4 tables: recovery_memory, simulated_dispatch_log, review_queue

Revision ID: 002_phase4
Revises: 001_initial
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "002_phase4"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cross-dialect types for PostgreSQL and SQLite compatibility
UUIDType = sa.CHAR(36).with_variant(UUID(as_uuid=True), "postgresql")


def upgrade() -> None:
    # --- recovery_memory ---
    op.create_table(
        "recovery_memory",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column(
            "customer_id",
            UUIDType,
            sa.ForeignKey("customers.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("typical_payment_day_of_month", sa.Integer, nullable=True),
        sa.Column("preferred_channel", sa.String(50), nullable=True),
        sa.Column(
            "preferred_language",
            sa.String(10),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "historical_response_rate",
            sa.Float,
            nullable=False,
            server_default="0.0",
        ),
        sa.Column("avg_response_latency_hours", sa.Float, nullable=True),
        sa.Column(
            "fatigue_score_last_computed",
            sa.Float,
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "last_updated", sa.DateTime(timezone=True), nullable=False
        ),
    )

    # --- simulated_dispatch_log ---
    op.create_table(
        "simulated_dispatch_log",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column(
            "customer_id",
            UUIDType,
            sa.ForeignKey("customers.id"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("message_body", sa.Text, nullable=False),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), nullable=False
        ),
    )

    # --- review_queue ---
    op.create_table(
        "review_queue",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column(
            "event_id",
            UUIDType,
            sa.ForeignKey("events.id"),
            nullable=True,
        ),
        sa.Column(
            "customer_id",
            UUIDType,
            sa.ForeignKey("customers.id"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "resolved",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_table("review_queue")
    op.drop_table("simulated_dispatch_log")
    op.drop_table("recovery_memory")

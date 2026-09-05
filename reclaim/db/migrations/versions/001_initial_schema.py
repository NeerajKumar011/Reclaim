"""Initial schema — events, customers, recovery_state, audit_log

Revision ID: 001_initial
Revises: None
Create Date: 2026-08-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cross-dialect types for PostgreSQL and SQLite compatibility
JSONType = sa.JSON().with_variant(JSONB, "postgresql")
UUIDType = sa.CHAR(36).with_variant(UUID(as_uuid=True), "postgresql")


def upgrade() -> None:
    # --- Enum types ---
    event_type_enum = sa.Enum(
        "payment_failed", "payment_captured", "order_paid",
        "subscription_charged", "subscription_halted", "payment_link_paid",
        "checkout_abandoned", "invoice_overdue",
        name="event_type_enum",
    )
    processing_status_enum = sa.Enum(
        "pending", "processed", "ignored_duplicate", "error",
        name="processing_status_enum",
    )
    recovery_state_enum = sa.Enum(
        "failed", "waiting", "nudged", "promised",
        "recovered", "escalated", "opted_out",
        name="recovery_state_enum",
    )

    # --- events ---
    op.create_table(
        "events",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("razorpay_event_id", sa.String(255), nullable=False, unique=True),
        sa.Column("event_type", event_type_enum, nullable=False),
        sa.Column("raw_payload", JSONType, nullable=False),
        sa.Column("normalized_payload", JSONType, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_status", processing_status_enum, nullable=False,
                  server_default="pending"),
    )
    op.create_index("ix_events_razorpay_event_id", "events", ["razorpay_event_id"])

    # --- customers ---
    op.create_table(
        "customers",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("razorpay_customer_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("preferred_language", sa.String(10), nullable=False,
                  server_default="en"),
        sa.Column("opted_out", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customers_razorpay_customer_id", "customers",
                    ["razorpay_customer_id"])
    op.create_index("ix_customers_email", "customers", ["email"])

    # --- recovery_state ---
    op.create_table(
        "recovery_state",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("customer_id", UUIDType,
                  sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("event_id", UUIDType,
                  sa.ForeignKey("events.id"), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("state", recovery_state_enum, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- audit_log ---
    op.create_table(
        "audit_log",
        sa.Column("id", UUIDType, primary_key=True),
        sa.Column("event_id", UUIDType,
                  sa.ForeignKey("events.id"), nullable=True),
        sa.Column("recovery_state_id", UUIDType,
                  sa.ForeignKey("recovery_state.id"), nullable=True),
        sa.Column("actor", sa.String(50), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("metadata", JSONType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("recovery_state")
    op.drop_table("customers")
    op.drop_table("events")
    sa.Enum(name="recovery_state_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="processing_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="event_type_enum").drop(op.get_bind(), checkfirst=True)

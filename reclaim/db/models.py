"""SQLAlchemy ORM models for RECLAIM.

Four tables: events, customers, recovery_state, audit_log.
All use UUID primary keys and store timestamps in UTC.
"""

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.types import TypeDecorator, CHAR
import uuid as uuid_pkg

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise uses CHAR(36).
    """
    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid_pkg.UUID):
            return str(value)
        return str(uuid_pkg.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid_pkg.UUID):
            return uuid_pkg.UUID(str(value))
        return value


# Cross-dialect JSON and UUID types
JSONType = JSON().with_variant(JSONB, "postgresql")
UUIDType = GUID()





def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventType(str, enum.Enum):
    payment_failed = "payment_failed"
    payment_captured = "payment_captured"
    order_paid = "order_paid"
    subscription_charged = "subscription_charged"
    subscription_halted = "subscription_halted"
    payment_link_paid = "payment_link_paid"
    checkout_abandoned = "checkout_abandoned"
    invoice_overdue = "invoice_overdue"


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processed = "processed"
    ignored_duplicate = "ignored_duplicate"
    error = "error"


class RecoveryStateEnum(str, enum.Enum):
    failed = "failed"
    waiting = "waiting"
    nudged = "nudged"
    promised = "promised"
    recovered = "recovered"
    escalated = "escalated"
    opted_out = "opted_out"


class ActorType(str, enum.Enum):
    system = "system"
    diagnosis_engine = "diagnosis_engine"
    policy_engine = "policy_engine"
    orchestrator = "orchestrator"
    human = "human"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=_new_uuid
    )
    razorpay_event_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type_enum", create_constraint=True),
        nullable=False,
    )
    raw_payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    normalized_payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status_enum", create_constraint=True),
        default=ProcessingStatus.pending,
        nullable=False,
    )

    # Relationships
    recovery_states: Mapped[list["RecoveryState"]] = relationship(
        back_populates="event"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="event")

    def __repr__(self) -> str:
        return f"<Event {self.razorpay_event_id} ({self.event_type.value})>"


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=_new_uuid
    )
    razorpay_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preferred_language: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False
    )
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Relationships
    recovery_states: Mapped[list["RecoveryState"]] = relationship(
        back_populates="customer"
    )
    recovery_memory: Mapped["RecoveryMemory | None"] = relationship(
        back_populates="customer", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Customer {self.email or self.razorpay_customer_id}>"


# ---------------------------------------------------------------------------
# Recovery Memory
# ---------------------------------------------------------------------------

class RecoveryMemory(Base):
    """Customer recovery profile and historical behavioral memory.

    DATA PROVENANCE GUARANTEE:
    All fields in RecoveryMemory are populated strictly from deterministic historical
    payment events and structured state transitions (via outcome_observer.py), NEVER
    hallucinated or guessed by the LLM.

    Field Provenance:
      - typical_payment_day_of_month: Day of month (1..31) computed from historical
        successful payment timestamps (payment.captured / order.paid) or explicit
        customer promise-to-pay intent.
      - preferred_channel: Attributed channel from historical successful conversions.
      - historical_response_rate: recovered_count / total_cases ratio for customer.
      - avg_response_latency_hours: Average hours from failure to capture.
      - fatigue_score_last_computed: Deterministic exponential decay of contact volume.
    """
    __tablename__ = "recovery_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=_new_uuid
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("customers.id"), unique=True, nullable=False
    )
    typical_payment_day_of_month: Mapped[int | None] = mapped_column(
        nullable=True
    )
    preferred_channel: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    preferred_language: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False
    )
    historical_response_rate: Mapped[float] = mapped_column(
        default=0.0, nullable=False
    )
    avg_response_latency_hours: Mapped[float | None] = mapped_column(
        nullable=True
    )
    fatigue_score_last_computed: Mapped[float] = mapped_column(
        default=0.0, nullable=False
    )
    promise_to_pay_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_outcome: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="recovery_memory")

    def __repr__(self) -> str:
        return f"<RecoveryMemory customer_id={self.customer_id} rate={self.historical_response_rate}>"


# ---------------------------------------------------------------------------
# Simulated Dispatch Log
# ---------------------------------------------------------------------------

class SimulatedDispatchLog(Base):
    __tablename__ = "simulated_dispatch_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=_new_uuid
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("customers.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<SimulatedDispatchLog {self.channel} to {self.customer_id}>"


# ---------------------------------------------------------------------------
# Review Queue
# ---------------------------------------------------------------------------

class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=_new_uuid
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("events.id"), nullable=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("customers.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<ReviewQueue {self.id} resolved={self.resolved}>"



# ---------------------------------------------------------------------------
# Recovery State
# ---------------------------------------------------------------------------

class RecoveryState(Base):
    __tablename__ = "recovery_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=_new_uuid
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("customers.id"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("events.id"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2), nullable=False
    )
    state: Mapped[RecoveryStateEnum] = mapped_column(
        Enum(RecoveryStateEnum, name="recovery_state_enum", create_constraint=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="recovery_states")
    event: Mapped["Event"] = relationship(back_populates="recovery_states")
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="recovery_state"
    )

    def __repr__(self) -> str:
        return f"<RecoveryState {self.id} state={self.state.value}>"


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=_new_uuid
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("events.id"), nullable=True
    )
    recovery_state_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("recovery_state.id"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONType, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Relationships
    event: Mapped["Event | None"] = relationship(back_populates="audit_logs")
    recovery_state: Mapped["RecoveryState | None"] = relationship(
        back_populates="audit_logs"
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} by {self.actor}>"

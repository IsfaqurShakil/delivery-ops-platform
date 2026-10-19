# app/models.py
# Database tables described as Python classes. All data in this project is fake.
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ShipmentStatus(enum.StrEnum):
    # The allowed states of a shipment. The state machine (later step) controls the moves between them.
    CREATED = "created"
    ASSIGNED = "assigned"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    ATTEMPT_FAILED = "attempt_failed"
    RESCHEDULED = "rescheduled"
    RETURN_TO_SENDER = "return_to_sender"


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Rider(Base):
    __tablename__ = "riders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    daily_capacity: Mapped[int] = mapped_column(Integer, default=20)  # max shipments per day
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_code: Mapped[str] = mapped_column(String(30), unique=True)
    recipient_name: Mapped[str] = mapped_column(String(100))
    recipient_phone: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(255))
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    rider_id: Mapped[int | None] = mapped_column(ForeignKey("riders.id"), default=None)  # empty until assigned
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(ShipmentStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=ShipmentStatus.CREATED,
        index=True,
    )
    is_cod: Mapped[bool] = mapped_column(Boolean, default=False)  # cash on delivery?
    cod_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    rider_id: Mapped[int | None] = mapped_column(ForeignKey("riders.id"), default=None)
    attempt_no: Mapped[int] = mapped_column(Integer)  # 1st, 2nd, 3rd attempt
    outcome: Mapped[str] = mapped_column(String(20))  # for example "delivered" or "failed"
    failure_reason: Mapped[str | None] = mapped_column(String(50), default=None)  # filled only when failed
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    # History of every change. Append-only by design: rows are only ever added.
    # No foreign key on purpose: the history must survive even if the original row is removed.
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30))  # for example "shipment"
    entity_id: Mapped[int] = mapped_column(Integer)  # the id of that shipment
    action: Mapped[str] = mapped_column(String(50))  # for example "status_change"
    old_value: Mapped[str | None] = mapped_column(String(50), default=None)
    new_value: Mapped[str | None] = mapped_column(String(50), default=None)
    actor: Mapped[str] = mapped_column(String(100), default="system")  # who did it
    details: Mapped[str | None] = mapped_column(Text, default=None)  # extra context as JSON text, for example the rule version
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    DISPATCHER = "dispatcher"
    RIDER = "rider"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # never the real password, only its hash
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    rider_id: Mapped[int | None] = mapped_column(ForeignKey("riders.id"), default=None)  # only for rider users
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExceptionTask(Base):
    # A piece of follow-up work created when a delivery fails, for example "send an SMS reminder"
    # or "customer service must call the recipient". Created by the exception rule engine.
    __tablename__ = "exception_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(50))  # "sms_reminder" or "customer_service_task"
    status: Mapped[str] = mapped_column(String(20), default="open")  # "open" until someone finishes it
    reason: Mapped[str | None] = mapped_column(String(50), default=None)  # the failure reason that caused it
    rule_version: Mapped[str] = mapped_column(String(20))  # which version of the rules created this task
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

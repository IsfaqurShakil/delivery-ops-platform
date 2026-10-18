# app/models.py
# Database tables described as Python classes. All data in this project is fake.
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
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

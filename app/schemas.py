# app/schemas.py
# Schemas describe what data the API accepts and returns. Pydantic checks them automatically.
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import ShipmentStatus


class ShipmentCreate(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=100)
    recipient_phone: str = Field(pattern=r"^01\d{9}$")  # Bangladesh mobile: 01 + 9 digits
    address: str = Field(min_length=1, max_length=255)
    zone_id: int
    is_cod: bool = False
    cod_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def check_cod_rules(self):
        if self.is_cod and self.cod_amount <= 0:
            raise ValueError("cod_amount must be greater than 0 when is_cod is true")
        if not self.is_cod and self.cod_amount != 0:
            raise ValueError("cod_amount must be 0 when is_cod is false")
        return self


class StatusChange(BaseModel):
    new_status: ShipmentStatus
    rider_id: int | None = None
    failure_reason: str | None = Field(default=None, max_length=50)


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # allows building this from a database object

    id: int
    tracking_code: str
    recipient_name: str
    recipient_phone: str
    address: str
    zone_id: int
    rider_id: int | None
    status: ShipmentStatus
    is_cod: bool
    cod_amount: Decimal
    attempt_count: int


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

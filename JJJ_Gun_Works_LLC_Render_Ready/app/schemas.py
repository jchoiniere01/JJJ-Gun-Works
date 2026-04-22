from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ApiMessage(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    database_name: str | None = None
    server_time: datetime | str | None = None


class PaginatedResponse(BaseModel):
    table: str
    page: int
    page_size: int
    total: int
    items: list[dict[str, Any]]


class InventoryCreate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class InventoryUpdate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class OrderCreate(BaseModel):
    customer_name: str | None = Field(default=None, max_length=200)
    customer_email: EmailStr | None = None
    customer_phone: str | None = Field(default=None, max_length=50)
    build_type: Literal["rifle", "pistol"] | None = None
    notes: str | None = None


class ReservationLineCreate(BaseModel):
    inventory_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class OrderReservationCreate(BaseModel):
    order: OrderCreate
    lines: list[ReservationLineCreate] = Field(min_length=1)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def unique_inventory_items(self) -> "OrderReservationCreate":
        ids = [line.inventory_item_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Reservation lines must not contain duplicate inventory_item_id values.")
        return self


class ReservationReleaseRequest(BaseModel):
    reservation_ids: list[int] | None = None
    order_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_target(self) -> "ReservationReleaseRequest":
        if not self.reservation_ids and not self.order_id:
            raise ValueError("Provide reservation_ids or order_id.")
        return self


class ReservationResponse(BaseModel):
    order_id: int
    reservations: list[dict[str, Any]]


class ConfiguratorOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inventory_item_id: int
    sku: str | None = None
    name: str
    manufacturer: str | None = None
    model: str | None = None
    caliber: str | None = None
    platform: str | None = None
    part_role: str
    build_type: str | None = None
    unit_price: Decimal | float | None = None
    quantity_available: int


class ConfiguratorOptionsResponse(BaseModel):
    build_type: Literal["rifle", "pistol"]
    lower_receiver: list[ConfiguratorOption]
    riser_mount: list[ConfiguratorOption]
    pistol_grip: list[ConfiguratorOption]

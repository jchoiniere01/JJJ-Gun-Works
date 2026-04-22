from datetime import datetime

from fastapi import APIRouter, Query, status

from app.schemas import OrderReservationCreate, ReservationReleaseRequest, ReservationResponse
from app.services.reservation_service import create_order_with_reservations, expire_reservations, release_reservations

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post("", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(payload: OrderReservationCreate) -> dict:
    return create_order_with_reservations(payload)


@router.post("/release")
def release_reservation(payload: ReservationReleaseRequest) -> dict:
    return release_reservations(payload)


@router.post("/expire")
def expire_active_reservations(as_of: datetime | None = Query(default=None)) -> dict:
    return expire_reservations(as_of)

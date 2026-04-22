from fastapi import APIRouter, HTTPException

from app.db import health_check
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    try:
        db_status = health_check()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {exc}") from exc
    return HealthResponse(status="ok", **db_status)

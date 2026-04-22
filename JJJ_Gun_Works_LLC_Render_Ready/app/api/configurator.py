from typing import Literal

from fastapi import APIRouter, Query

from app.schemas import ConfiguratorOptionsResponse
from app.services.configurator_service import get_build_options, get_part_options

router = APIRouter(prefix="/configurator", tags=["configurator"])


@router.get("/{build_type}/options", response_model=ConfiguratorOptionsResponse)
def get_configurator_options(build_type: Literal["rifle", "pistol"]) -> dict:
    """Return five available options each for lower receiver, riser mount, and pistol grip."""

    return get_build_options(build_type)


@router.get("/{build_type}/parts/{part_role}")
def get_configurator_part_options(
    build_type: Literal["rifle", "pistol"],
    part_role: Literal["lower_receiver", "riser_mount", "pistol_grip"],
    limit: int = Query(default=5, ge=1, le=25),
) -> dict:
    return {"build_type": build_type, "part_role": part_role, "items": get_part_options(build_type, part_role, limit)}

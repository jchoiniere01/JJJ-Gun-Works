from __future__ import annotations

from typing import Literal

from app.db import execute_query


PART_ROLES = {
    "lower_receiver": ("lower receiver", "lower_receiver", "lower"),
    "riser_mount": ("riser mount", "riser_mount", "riser"),
    "pistol_grip": ("pistol grip", "pistol_grip", "grip"),
}


def get_part_options(build_type: Literal["rifle", "pistol"], part_role: str, limit: int = 5) -> list[dict]:
    role_values = PART_ROLES[part_role]
    placeholders = ", ".join("%s" for _ in role_values)
    sql = f"""
        SELECT
            inventory_item_id,
            sku,
            name,
            manufacturer,
            model,
            caliber,
            platform,
            part_role,
            build_type,
            unit_price,
            quantity_on_hand - quantity_reserved AS quantity_available
        FROM public.inventory_items
        WHERE
            is_active = TRUE
            AND quantity_on_hand - quantity_reserved > 0
            AND LOWER(part_role) IN ({placeholders})
            AND (
                build_type IS NULL
                OR LOWER(build_type) IN (%s, 'both', 'any', 'rifle/pistol')
            )
        ORDER BY
            CASE WHEN LOWER(build_type) = %s THEN 0 ELSE 1 END,
            quantity_on_hand - quantity_reserved DESC,
            name ASC
        LIMIT %s;
    """
    return execute_query(sql, (*role_values, build_type, build_type, limit))


def get_build_options(build_type: Literal["rifle", "pistol"]) -> dict:
    return {
        "build_type": build_type,
        "lower_receiver": get_part_options(build_type, "lower_receiver", 5),
        "riser_mount": get_part_options(build_type, "riser_mount", 5),
        "pistol_grip": get_part_options(build_type, "pistol_grip", 5),
    }

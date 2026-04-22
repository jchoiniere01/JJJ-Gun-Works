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
    placeholders = ", ".join("?" for _ in role_values)
    sql = f"""
        SELECT TOP (?)
            InventoryItemID AS inventory_item_id,
            SKU AS sku,
            Name AS name,
            Manufacturer AS manufacturer,
            Model AS model,
            Caliber AS caliber,
            Platform AS platform,
            PartRole AS part_role,
            BuildType AS build_type,
            UnitPrice AS unit_price,
            QuantityOnHand - QuantityReserved AS quantity_available
        FROM dbo.InventoryItems
        WHERE
            IsActive = 1
            AND QuantityOnHand - QuantityReserved > 0
            AND LOWER(PartRole) IN ({placeholders})
            AND (
                BuildType IS NULL
                OR LOWER(BuildType) IN (?, 'both', 'any', 'rifle/pistol')
            )
        ORDER BY
            CASE WHEN LOWER(BuildType) = ? THEN 0 ELSE 1 END,
            QuantityOnHand - QuantityReserved DESC,
            Name ASC;
    """
    return execute_query(sql, (limit, *role_values, build_type, build_type))


def get_build_options(build_type: Literal["rifle", "pistol"]) -> dict:
    return {
        "build_type": build_type,
        "lower_receiver": get_part_options(build_type, "lower_receiver", 5),
        "riser_mount": get_part_options(build_type, "riser_mount", 5),
        "pistol_grip": get_part_options(build_type, "pistol_grip", 5),
    }

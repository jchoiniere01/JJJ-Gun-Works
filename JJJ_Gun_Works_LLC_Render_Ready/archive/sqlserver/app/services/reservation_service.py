from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pyodbc
from fastapi import HTTPException, status

from app.db import row_to_dict, rows_to_dicts, transaction_scope
from app.schemas import OrderReservationCreate, ReservationReleaseRequest


def _insert_order(cursor: pyodbc.Cursor, payload: OrderReservationCreate) -> int:
    cursor.execute(
        """
        INSERT INTO dbo.Orders
            (CustomerName, CustomerEmail, CustomerPhone, OrderStatus, BuildType, Notes, CreatedAt, UpdatedAt)
        VALUES (?, ?, ?, 'reserved', ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME());
        """,
        (
            payload.order.customer_name,
            str(payload.order.customer_email) if payload.order.customer_email else None,
            payload.order.customer_phone,
            payload.order.build_type,
            payload.order.notes,
        ),
    )
    cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT) AS OrderID;")
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create order.")
    return int(row[0])


def create_order_with_reservations(payload: OrderReservationCreate) -> dict[str, Any]:
    """Create an order and reserve inventory with atomic oversell protection.

    The key protection is the guarded UPDATE:

        QuantityOnHand - QuantityReserved >= requested_quantity

    SQL Server takes update locks on the target row, so concurrent requests cannot
    reserve the same available quantity. The included T-SQL trigger is still useful
    as a database-level backstop for manual writes and other clients.
    """

    with transaction_scope() as conn:
        cursor = conn.cursor()
        order_id = _insert_order(cursor, payload)
        reservations: list[dict[str, Any]] = []

        for line in payload.lines:
            cursor.execute(
                """
                UPDATE dbo.InventoryItems WITH (UPDLOCK, HOLDLOCK)
                SET
                    QuantityReserved = QuantityReserved + ?,
                    UpdatedAt = SYSUTCDATETIME()
                WHERE
                    InventoryItemID = ?
                    AND IsActive = 1
                    AND QuantityOnHand - QuantityReserved >= ?;
                """,
                (line.quantity, line.inventory_item_id, line.quantity),
            )
            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Insufficient available inventory for item {line.inventory_item_id}; reservation was rolled back.",
                )
            cursor.execute(
                """
                SELECT
                    InventoryItemID,
                    SKU,
                    Name,
                    QuantityOnHand,
                    QuantityReserved,
                    QuantityOnHand - QuantityReserved AS QuantityAvailable
                FROM dbo.InventoryItems
                WHERE InventoryItemID = ?;
                """,
                line.inventory_item_id,
            )
            reserved_item = row_to_dict(cursor)

            cursor.execute(
                """
                INSERT INTO dbo.OrderReservations
                    (OrderID, InventoryItemID, Quantity, ReservationStatus, ExpiresAt, CreatedAt, UpdatedAt)
                VALUES (?, ?, ?, 'active', ?, SYSUTCDATETIME(), SYSUTCDATETIME());
                """,
                (
                    order_id,
                    line.inventory_item_id,
                    line.quantity,
                    payload.expires_at,
                ),
            )
            cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT) AS ReservationID;")
            inserted_reservation = row_to_dict(cursor)
            cursor.execute(
                "SELECT * FROM dbo.OrderReservations WHERE ReservationID = ?;",
                int(inserted_reservation["ReservationID"]),
            )
            reservation = row_to_dict(cursor)
            if not reservation:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create reservation.")
            reservation["reserved_item"] = reserved_item
            reservations.append(reservation)

    return {"order_id": order_id, "reservations": reservations}


def release_reservations(payload: ReservationReleaseRequest) -> dict[str, Any]:
    reservation_ids = payload.reservation_ids or []
    released: list[dict[str, Any]] = []

    with transaction_scope() as conn:
        cursor = conn.cursor()
        if reservation_ids:
            placeholders = ", ".join("?" for _ in reservation_ids)
            cursor.execute(
                f"""
                SELECT *
                FROM dbo.OrderReservations WITH (UPDLOCK, HOLDLOCK)
                WHERE ReservationStatus = 'active'
                  AND ReservationID IN ({placeholders});
                """,
                tuple(reservation_ids),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM dbo.OrderReservations WITH (UPDLOCK, HOLDLOCK)
                WHERE ReservationStatus = 'active'
                  AND OrderID = ?;
                """,
                payload.order_id,
            )

        active_reservations = rows_to_dicts(cursor)
        if not active_reservations:
            return {"released_count": 0, "released": []}

        for reservation in active_reservations:
            cursor.execute(
                """
                UPDATE dbo.InventoryItems WITH (UPDLOCK, HOLDLOCK)
                SET
                    QuantityReserved =
                        CASE
                            WHEN QuantityReserved - ? < 0 THEN 0
                            ELSE QuantityReserved - ?
                        END,
                    UpdatedAt = SYSUTCDATETIME()
                WHERE InventoryItemID = ?;
                """,
                (
                    reservation["Quantity"],
                    reservation["Quantity"],
                    reservation["InventoryItemID"],
                ),
            )
            cursor.execute(
                """
                UPDATE dbo.OrderReservations
                SET ReservationStatus = 'released',
                    UpdatedAt = SYSUTCDATETIME()
                WHERE ReservationID = ?;
                """,
                reservation["ReservationID"],
            )
            cursor.execute(
                "SELECT * FROM dbo.OrderReservations WHERE ReservationID = ?;",
                reservation["ReservationID"],
            )
            released_row = row_to_dict(cursor)
            if released_row:
                released.append(released_row)

    return {"released_count": len(released), "released": released}


def expire_reservations(as_of: datetime | None = None) -> dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc)
    with transaction_scope() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM dbo.OrderReservations WITH (UPDLOCK, HOLDLOCK)
            WHERE ReservationStatus = 'active'
              AND ExpiresAt IS NOT NULL
              AND ExpiresAt <= ?;
            """,
            as_of,
        )
        rows = rows_to_dicts(cursor)

        for reservation in rows:
            cursor.execute(
                """
                UPDATE dbo.InventoryItems WITH (UPDLOCK, HOLDLOCK)
                SET QuantityReserved =
                        CASE
                            WHEN QuantityReserved - ? < 0 THEN 0
                            ELSE QuantityReserved - ?
                        END,
                    UpdatedAt = SYSUTCDATETIME()
                WHERE InventoryItemID = ?;
                """,
                reservation["Quantity"],
                reservation["Quantity"],
                reservation["InventoryItemID"],
            )
            cursor.execute(
                """
                UPDATE dbo.OrderReservations
                SET ReservationStatus = 'expired',
                    UpdatedAt = SYSUTCDATETIME()
                WHERE ReservationID = ?;
                """,
                reservation["ReservationID"],
            )

    return {"expired_count": len(rows), "expired_reservation_ids": [row["ReservationID"] for row in rows]}

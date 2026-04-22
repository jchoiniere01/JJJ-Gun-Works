from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import psycopg
from fastapi import HTTPException, status

from app.db import row_to_dict, rows_to_dicts, transaction_scope
from app.schemas import OrderReservationCreate, ReservationReleaseRequest


def _insert_order(cursor: psycopg.Cursor, payload: OrderReservationCreate) -> int:
    cursor.execute(
        """
        INSERT INTO public.orders
            (customer_name, customer_email, customer_phone, order_status, build_type, notes, created_at, updated_at)
        VALUES (%s, %s, %s, 'reserved', %s, %s, now(), now())
        RETURNING order_id;
        """,
        (
            payload.order.customer_name,
            str(payload.order.customer_email) if payload.order.customer_email else None,
            payload.order.customer_phone,
            payload.order.build_type,
            payload.order.notes,
        ),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create order.")
    # dict_row factory returns {"order_id": <int>}.
    return int(row["order_id"])


def create_order_with_reservations(payload: OrderReservationCreate) -> dict[str, Any]:
    """Create an order and reserve inventory with atomic oversell protection.

    The key protection is the guarded UPDATE:

        quantity_on_hand - quantity_reserved >= requested_quantity

    PostgreSQL takes a row-level lock on every matched row inside the
    UPDATE, so concurrent requests cannot reserve the same available
    quantity. The plpgsql trigger ``inventory_items_no_oversell`` in
    ``sql/postgres/001_*.sql`` is a database-level backstop for manual
    writes and other non-API clients.
    """

    with transaction_scope() as conn:
        with conn.cursor() as cursor:
            order_id = _insert_order(cursor, payload)
            reservations: list[dict[str, Any]] = []

            for line in payload.lines:
                cursor.execute(
                    """
                    UPDATE public.inventory_items
                       SET quantity_reserved = quantity_reserved + %s,
                           updated_at        = now()
                     WHERE inventory_item_id = %s
                       AND is_active = TRUE
                       AND quantity_on_hand - quantity_reserved >= %s;
                    """,
                    (line.quantity, line.inventory_item_id, line.quantity),
                )
                if cursor.rowcount == 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Insufficient available inventory for item {line.inventory_item_id}; "
                            "reservation was rolled back."
                        ),
                    )
                cursor.execute(
                    """
                    SELECT
                        inventory_item_id,
                        sku,
                        name,
                        quantity_on_hand,
                        quantity_reserved,
                        quantity_on_hand - quantity_reserved AS quantity_available
                    FROM public.inventory_items
                    WHERE inventory_item_id = %s;
                    """,
                    (line.inventory_item_id,),
                )
                reserved_item = row_to_dict(cursor)

                cursor.execute(
                    """
                    INSERT INTO public.order_reservations
                        (order_id, inventory_item_id, quantity, reservation_status, expires_at, created_at, updated_at)
                    VALUES (%s, %s, %s, 'active', %s, now(), now())
                    RETURNING *;
                    """,
                    (
                        order_id,
                        line.inventory_item_id,
                        line.quantity,
                        payload.expires_at,
                    ),
                )
                reservation = row_to_dict(cursor)
                if not reservation:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to create reservation.",
                    )
                reservation["reserved_item"] = reserved_item
                reservations.append(reservation)

    return {"order_id": order_id, "reservations": reservations}


def release_reservations(payload: ReservationReleaseRequest) -> dict[str, Any]:
    reservation_ids = payload.reservation_ids or []
    released: list[dict[str, Any]] = []

    with transaction_scope() as conn:
        with conn.cursor() as cursor:
            if reservation_ids:
                placeholders = ", ".join("%s" for _ in reservation_ids)
                # FOR UPDATE mirrors the SQL Server (UPDLOCK, HOLDLOCK) hint,
                # locking matching rows for the duration of this transaction.
                cursor.execute(
                    f"""
                    SELECT *
                      FROM public.order_reservations
                     WHERE reservation_status = 'active'
                       AND reservation_id IN ({placeholders})
                       FOR UPDATE;
                    """,
                    tuple(reservation_ids),
                )
            else:
                cursor.execute(
                    """
                    SELECT *
                      FROM public.order_reservations
                     WHERE reservation_status = 'active'
                       AND order_id = %s
                       FOR UPDATE;
                    """,
                    (payload.order_id,),
                )

            active_reservations = rows_to_dicts(cursor)
            if not active_reservations:
                return {"released_count": 0, "released": []}

            for reservation in active_reservations:
                cursor.execute(
                    """
                    UPDATE public.inventory_items
                       SET quantity_reserved = GREATEST(quantity_reserved - %s, 0),
                           updated_at        = now()
                     WHERE inventory_item_id = %s;
                    """,
                    (reservation["quantity"], reservation["inventory_item_id"]),
                )
                cursor.execute(
                    """
                    UPDATE public.order_reservations
                       SET reservation_status = 'released',
                           updated_at         = now()
                     WHERE reservation_id = %s
                    RETURNING *;
                    """,
                    (reservation["reservation_id"],),
                )
                released_row = row_to_dict(cursor)
                if released_row:
                    released.append(released_row)

    return {"released_count": len(released), "released": released}


def expire_reservations(as_of: datetime | None = None) -> dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc)
    with transaction_scope() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                  FROM public.order_reservations
                 WHERE reservation_status = 'active'
                   AND expires_at IS NOT NULL
                   AND expires_at <= %s
                   FOR UPDATE;
                """,
                (as_of,),
            )
            rows = rows_to_dicts(cursor)

            for reservation in rows:
                cursor.execute(
                    """
                    UPDATE public.inventory_items
                       SET quantity_reserved = GREATEST(quantity_reserved - %s, 0),
                           updated_at        = now()
                     WHERE inventory_item_id = %s;
                    """,
                    (reservation["quantity"], reservation["inventory_item_id"]),
                )
                cursor.execute(
                    """
                    UPDATE public.order_reservations
                       SET reservation_status = 'expired',
                           updated_at         = now()
                     WHERE reservation_id = %s;
                    """,
                    (reservation["reservation_id"],),
                )

    return {
        "expired_count": len(rows),
        "expired_reservation_ids": [row["reservation_id"] for row in rows],
    }

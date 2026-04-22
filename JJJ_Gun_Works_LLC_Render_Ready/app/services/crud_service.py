from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status

from app.db import connection_scope, row_to_dict, rows_to_dicts, transaction_scope
from app.sql_utils import TableMapping, quote_identifier


CONTROL_QUERY_PARAMS = {"page", "page_size", "q", "order_by", "order_dir"}


def build_where_clause(mapping: TableMapping, request: Request) -> tuple[str, list[Any]]:
    """Construct a WHERE clause from search (``q``) and column-equality filters.

    Uses ``ILIKE`` (case-insensitive LIKE) over a text cast of each searchable
    column to mirror the case-insensitive behavior of SQL Server's default
    collation.
    """

    clauses: list[str] = []
    params: list[Any] = []

    q = request.query_params.get("q")
    if q and mapping.searchable_columns:
        search_clauses = [
            f"CAST({quote_identifier(column)} AS TEXT) ILIKE %s"
            for column in mapping.searchable_columns
        ]
        clauses.append("(" + " OR ".join(search_clauses) + ")")
        params.extend([f"%{q}%"] * len(search_clauses))

    for key, value in request.query_params.multi_items():
        if key in CONTROL_QUERY_PARAMS or value == "":
            continue
        if key not in mapping.allowed_columns and key != mapping.primary_key:
            continue
        clauses.append(f"{quote_identifier(key)} = %s")
        params.append(value)

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def list_rows(mapping: TableMapping, request: Request, page: int, page_size: int) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    offset = (page - 1) * page_size

    where_clause, params = build_where_clause(mapping, request)
    order_by = request.query_params.get("order_by") or mapping.default_order_by or mapping.primary_key
    if order_by not in mapping.allowed_columns and order_by != mapping.primary_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported order_by column: {order_by}")
    order_dir = request.query_params.get("order_dir", "asc").lower()
    if order_dir not in {"asc", "desc"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_dir must be 'asc' or 'desc'.")

    sql_count = f"SELECT COUNT(1) AS total FROM {mapping.qualified_name}{where_clause};"
    sql_list = f"""
        SELECT *
        FROM {mapping.qualified_name}
        {where_clause}
        ORDER BY {quote_identifier(order_by)} {order_dir.upper()}
        LIMIT %s OFFSET %s;
    """

    with connection_scope() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql_count, tuple(params))
            count_row = cursor.fetchone()
            # dict_row yields e.g. {"total": 42}
            total = int(count_row["total"]) if count_row else 0
            cursor.execute(sql_list, tuple(params) + (page_size, offset))
            items = rows_to_dicts(cursor)

    return {"table": mapping.key, "page": page, "page_size": page_size, "total": total, "items": items}


def get_row(mapping: TableMapping, row_id: int) -> dict[str, Any]:
    sql = f"SELECT * FROM {mapping.qualified_name} WHERE {quote_identifier(mapping.primary_key)} = %s;"
    with connection_scope() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (row_id,))
            row = row_to_dict(cursor)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{mapping.key} row not found.")
    return row


def create_row(mapping: TableMapping, data: dict[str, Any]) -> dict[str, Any]:
    payload = mapping.allowed_payload(data)
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No allowed fields were provided.")

    columns = list(payload.keys())
    col_sql = ", ".join(quote_identifier(column) for column in columns)
    placeholders = ", ".join("%s" for _ in columns)
    sql = f"""
        INSERT INTO {mapping.qualified_name} ({col_sql})
        VALUES ({placeholders})
        RETURNING *;
    """

    with transaction_scope() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(payload[column] for column in columns))
            row = row_to_dict(cursor)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Insert did not return a row.",
        )
    return row


def update_row(mapping: TableMapping, row_id: int, data: dict[str, Any]) -> dict[str, Any]:
    payload = mapping.allowed_payload(data)
    payload.pop(mapping.primary_key, None)
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No allowed fields were provided.")

    assignments = ", ".join(f"{quote_identifier(column)} = %s" for column in payload)
    sql = f"""
        UPDATE {mapping.qualified_name}
        SET {assignments}
        WHERE {quote_identifier(mapping.primary_key)} = %s
        RETURNING *;
    """

    with transaction_scope() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(payload.values()) + (row_id,))
            row = row_to_dict(cursor)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{mapping.key} row not found.")
    return row


def delete_row(mapping: TableMapping, row_id: int) -> dict[str, Any]:
    sql = f"""
        DELETE FROM {mapping.qualified_name}
        WHERE {quote_identifier(mapping.primary_key)} = %s
        RETURNING *;
    """
    with transaction_scope() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (row_id,))
            row = row_to_dict(cursor)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{mapping.key} row not found.")
    return row

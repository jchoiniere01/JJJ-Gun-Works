from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Sequence

import pyodbc

from app.config import get_settings


pyodbc.pooling = True


class DatabaseError(RuntimeError):
    """Raised when an expected database operation fails."""


def get_connection(autocommit: bool = False) -> pyodbc.Connection:
    """Open a SQL Server connection.

    pyodbc has process-level pooling enabled above, so opening/closing per request
    is fine for this service and keeps transaction boundaries explicit.
    """

    conn = pyodbc.connect(get_settings().odbc_connection_string, autocommit=autocommit)
    return conn


@contextmanager
def connection_scope(autocommit: bool = False) -> Iterator[pyodbc.Connection]:
    conn = get_connection(autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction_scope() -> Iterator[pyodbc.Connection]:
    conn = get_connection(autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows_to_dicts(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description or []]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def row_to_dict(cursor: pyodbc.Cursor) -> dict[str, Any] | None:
    columns = [column[0] for column in cursor.description or []]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def execute_query(sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(params or ()))
        return rows_to_dicts(cursor)


def execute_one(sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
    with connection_scope() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(params or ()))
        return row_to_dict(cursor)


def execute_non_query(sql: str, params: Sequence[Any] | None = None) -> int:
    with transaction_scope() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(params or ()))
        affected = cursor.rowcount
        return affected if affected is not None else 0


def execute_many(sql: str, param_rows: Iterable[Sequence[Any]]) -> int:
    with transaction_scope() as conn:
        cursor = conn.cursor()
        cursor.fast_executemany = True
        cursor.executemany(sql, list(param_rows))
        affected = cursor.rowcount
        return affected if affected is not None else 0


def health_check() -> dict[str, Any]:
    result = execute_one("SELECT DB_NAME() AS database_name, SYSDATETIME() AS server_time;")
    return result or {"database_name": None, "server_time": None}

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings


class DatabaseError(RuntimeError):
    """Raised when an expected database operation fails."""


_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    """Lazy-construct a process-wide psycopg connection pool.

    Render Starter Postgres instances have low connection limits, so the
    pool is intentionally small. Bump ``max_size`` for larger plans.
    """

    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=get_settings().dsn,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
        )
    return _pool


@contextmanager
def connection_scope(autocommit: bool = False) -> Iterator[psycopg.Connection]:
    with _get_pool().connection() as conn:
        if conn.autocommit != autocommit:
            conn.autocommit = autocommit
        yield conn


@contextmanager
def transaction_scope() -> Iterator[psycopg.Connection]:
    """Execute inside an explicit transaction; commit on success, rollback on error."""

    with _get_pool().connection() as conn:
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def rows_to_dicts(cursor: psycopg.Cursor) -> list[dict[str, Any]]:
    # With row_factory=dict_row, fetchall() already returns list[dict[str, Any]].
    return list(cursor.fetchall())


def row_to_dict(cursor: psycopg.Cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    return dict(row) if row else None


def execute_query(sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    with connection_scope() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params or ()))
            return rows_to_dicts(cursor)


def execute_one(sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
    with connection_scope() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params or ()))
            return row_to_dict(cursor)


def execute_non_query(sql: str, params: Sequence[Any] | None = None) -> int:
    with transaction_scope() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params or ()))
            affected = cursor.rowcount
            return affected if affected is not None else 0


def execute_many(sql: str, param_rows: Iterable[Sequence[Any]]) -> int:
    with transaction_scope() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(sql, list(param_rows))
            affected = cursor.rowcount
            return affected if affected is not None else 0


def health_check() -> dict[str, Any]:
    result = execute_one(
        "SELECT current_database() AS database_name, now() AS server_time;"
    )
    return result or {"database_name": None, "server_time": None}

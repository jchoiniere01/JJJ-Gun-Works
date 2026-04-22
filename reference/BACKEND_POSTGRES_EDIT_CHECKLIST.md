# Backend Postgres Edit Checklist

This is a file-by-file checklist of the exact patterns to update in the
working copy of `JJJ_Gun_Works_LLC_extracted/JJJ Gun Works LLC`. Nothing
here modifies the original extract — apply each change to your clone.

Each section lists:
- **Files** involved
- **Patterns to find** (before)
- **Replacement** (after)
- Any cross-file implications

Assumptions: you are switching to `psycopg` 3 (the `psycopg[binary]`
package), keeping the same FastAPI router layout, and renaming tables to
`public.*` snake_case to match `sql/001_inventory_reservations.postgres.sql`.

---

## 1. `requirements.txt`

**Find**
```
pyodbc==5.2.0
```

**Replace with**
```
psycopg[binary]==3.2.3
psycopg-pool==3.2.3
```

Everything else (`fastapi`, `uvicorn[standard]`, `pydantic`,
`pydantic-settings`, `email-validator`, `python-dotenv`,
`python-multipart`) stays.

---

## 2. `pyproject.toml`

**Find**
```
description = "FastAPI backend for firearms inventory and AR configurator with SQL Server pyodbc."
```

**Replace with**
```
description = "FastAPI backend for firearms inventory and AR configurator on PostgreSQL (Render)."
```

---

## 3. `.env.example`

Replace the entire contents with the template from `.env.render.example`
in this package. In particular: delete every `SQLSERVER_*` line and add
`DATABASE_URL=...`.

---

## 4. `app/JJJGW.env`

**Delete the file.** It declares `DB_SERVER / DB_NAME / DB_DRIVER /
DB_TRUSTED` but is not read by the Settings class. Keeping it around only
confuses future readers.

Also update `.gitignore` to add:

```
app/*.env
```

so stray env files are never committed again.

---

## 5. `app/config.py`

**Remove** every `sqlserver_*` field and the `odbc_connection_string`
property.

**Replace** with a Postgres-friendly configuration. Suggested full
contents:

```python
from functools import lru_cache
from typing import List
from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application and PostgreSQL settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Firearms Inventory API"
    app_env: str = "local"
    api_prefix: str = "/api"
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    # Primary: a full libpq URI, e.g. Render's DATABASE_URL.
    database_url: str | None = None

    # Optional fallback if DATABASE_URL is unset.
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "firearms_inventory"
    pg_user: str = "firearms_app"
    pg_password: str | None = None
    pg_sslmode: str = "prefer"
    pg_timeout_seconds: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def dsn(self) -> str:
        if self.database_url:
            return self.database_url
        user = quote_plus(self.pg_user)
        pwd = quote_plus(self.pg_password) if self.pg_password else ""
        auth = f"{user}:{pwd}@" if pwd else f"{user}@"
        return (
            f"postgresql://{auth}{self.pg_host}:{self.pg_port}/{self.pg_database}"
            f"?sslmode={self.pg_sslmode}&connect_timeout={self.pg_timeout_seconds}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

---

## 6. `app/db.py`

**Replace the whole file.** Key changes: drop `pyodbc`, switch to
`psycopg` 3 with a connection pool, change the health check SQL, drop
`fast_executemany`.

```python
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
    with _get_pool().connection() as conn:
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def rows_to_dicts(cursor: psycopg.Cursor) -> list[dict[str, Any]]:
    # With row_factory=dict_row, fetchall already returns list[dict[str, Any]].
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
            return cursor.rowcount or 0


def execute_many(sql: str, param_rows: Iterable[Sequence[Any]]) -> int:
    with transaction_scope() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(sql, list(param_rows))
            return cursor.rowcount or 0


def health_check() -> dict[str, Any]:
    result = execute_one(
        "SELECT current_database() AS database_name, now() AS server_time;"
    )
    return result or {"database_name": None, "server_time": None}
```

Note: `psycopg` uses `%s` as the positional placeholder (not `?`). Every
call site in the service layer must be updated (sections below).

---

## 7. `app/sql_utils.py`

**Find**
```python
def quote_identifier(identifier: str) -> str:
    """Safely quote a SQL Server identifier that has already been whitelisted."""
    return "[" + identifier.replace("]", "]]") + "]"
```

**Replace with**
```python
def quote_identifier(identifier: str) -> str:
    """Safely quote a PostgreSQL identifier that has already been whitelisted."""
    return '"' + identifier.replace('"', '""') + '"'
```

`qualify_table` and `TableMapping` stay as-is.

---

## 8. `app/table_config.py`

Switch every mapping to the new schema/table/column names. Both the
`schema` and the `allowed_columns` tuples change. A minimal diff:

**Find** every occurrence of:
```python
schema="dbo",
```
**Replace** with:
```python
schema="public",
```

**Find** the tables:

| Before (T-SQL) | After (PG) |
| --- | --- |
| `table="InventoryItems"` | `table="inventory_items"` |
| `table="PartCategories"` | `table="part_categories"` |
| `table="Suppliers"` | `table="suppliers"` |
| `table="StockMovements"` | `table="stock_movements"` |
| `table="Orders"` | `table="orders"` |
| `table="OrderReservations"` | `table="order_reservations"` |

**Find** each `primary_key=`:

| Before | After |
| --- | --- |
| `InventoryItemID` | `inventory_item_id` |
| `CategoryID` | `category_id` |
| `SupplierID` | `supplier_id` |
| `StockMovementID` | `stock_movement_id` |
| `OrderID` | `order_id` |
| `ReservationID` | `reservation_id` |

**Find** each column name inside `allowed_columns` / `searchable_columns`
/ `default_order_by` and replace using `migration/tables.txt` (examples:
`SKU` → `sku`, `Name` → `name`, `QuantityOnHand` → `quantity_on_hand`,
`CreatedAt` → `created_at`, etc.).

Important: these identifiers are also returned to API clients as JSON
keys. Make sure any frontend consumer that reads `InventoryItemID` etc.
is updated, or alias the columns in the SELECT list. The existing API
response for `configurator` already aliases to snake_case, so that
endpoint is unaffected.

---

## 9. `app/services/crud_service.py`

| Pattern (find) | Replacement (after) |
| --- | --- |
| `?` in any SQL string | `%s` |
| `f"CAST({quote_identifier(column)} AS NVARCHAR(MAX)) LIKE ?"` | `f"CAST({quote_identifier(column)} AS TEXT) ILIKE %s"` |
| `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` | `LIMIT %s OFFSET %s` (and swap the params: put `page_size` before `offset`, or use `"LIMIT %s OFFSET %s"` with `tuple(params + [page_size, offset])`) |
| `cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT) AS inserted_id;")` + second INSERT re-fetch | Single statement: `INSERT INTO {qualified_name} ({cols}) VALUES ({placeholders}) RETURNING *;` — drop the follow-up SELECT. |
| `cursor.execute(sql, row_id)` with a scalar | Wrap scalars in a tuple: `cursor.execute(sql, (row_id,))` — psycopg is stricter than pyodbc about this. |

After the changes, a typical list SQL looks like:

```python
sql_list = f"""
    SELECT *
    FROM {mapping.qualified_name}
    {where_clause}
    ORDER BY {quote_identifier(order_by)} {order_dir.upper()}
    LIMIT %s OFFSET %s;
"""
# ...
cursor.execute(sql_list, tuple(params) + (page_size, offset))
```

---

## 10. `app/services/reservation_service.py`

| Pattern (find) | Replacement |
| --- | --- |
| `import pyodbc` and `pyodbc.Cursor` type hints | `import psycopg` and `psycopg.Cursor` |
| `dbo.Orders`, `dbo.InventoryItems`, `dbo.OrderReservations` (in SQL strings) | `public.orders`, `public.inventory_items`, `public.order_reservations` |
| All `?` | `%s` |
| `WITH (UPDLOCK, HOLDLOCK)` table hints (lines 55, 126, 150, 193, 205 in the original) | Remove entirely. For SELECTs that must lock reservation rows before updating them, use `FOR UPDATE` on the SELECT. |
| `SYSUTCDATETIME()` | `now()` (store as `TIMESTAMPTZ`) |
| `INSERT INTO dbo.Orders ... VALUES (...);` + `SELECT CAST(SCOPE_IDENTITY() AS INT) AS OrderID;` | Single statement: `INSERT INTO public.orders (customer_name, customer_email, customer_phone, order_status, build_type, notes) VALUES (%s, %s, %s, 'reserved', %s, %s) RETURNING order_id;` then read `row["order_id"]`. |
| `INSERT INTO dbo.OrderReservations ... ;` + `SELECT CAST(SCOPE_IDENTITY() AS INT)` + follow-up `SELECT *` | Single statement: `INSERT INTO public.order_reservations (...) VALUES (...) RETURNING *;` |
| `cursor.execute(sql, payload.order.customer_name, ...)` positional | `cursor.execute(sql, (payload.order.customer_name, ...))` (tuple) |
| Column names in returned dicts: `InventoryItemID`, `Quantity`, `ReservationID`, `QuantityOnHand`, `QuantityReserved` | `inventory_item_id`, `quantity`, `reservation_id`, `quantity_on_hand`, `quantity_reserved` |

Example of the key guarded UPDATE after translation:

```python
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
        detail=f"Insufficient available inventory for item {line.inventory_item_id}; reservation was rolled back.",
    )
```

`release_reservations` and `expire_reservations` translate the same way.
Where the original used `WITH (UPDLOCK, HOLDLOCK)` on the SELECT, append
`FOR UPDATE` to the PG SELECT.

---

## 11. `app/services/configurator_service.py`

| Pattern | Replacement |
| --- | --- |
| `SELECT TOP (?) ...` | `SELECT ... LIMIT %s` at the end of the statement. |
| All `?` placeholders | `%s`. |
| `dbo.InventoryItems` | `public.inventory_items`. |
| Column references in WHERE/ORDER BY (`IsActive`, `QuantityOnHand`, `QuantityReserved`, `PartRole`, `BuildType`, `Name`) | snake_case (`is_active`, `quantity_on_hand`, `quantity_reserved`, `part_role`, `build_type`, `name`). |
| Column references in SELECT list aliases (e.g., `InventoryItemID AS inventory_item_id`) | Change the left side to snake_case (`inventory_item_id AS inventory_item_id`) — or simplify to `SELECT inventory_item_id, ...` without aliasing. |
| `IsActive = 1` | `is_active = TRUE`. |

Because `get_part_options` currently passes `limit` as the first bound
parameter (for `TOP`), move it to the tail of the tuple after the change
to `LIMIT`. Full translated statement:

```python
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
```

---

## 12. `app/api/*.py`

No API router files need direct edits — they only import schemas and
services. However, because `app/table_config.py` allowed_columns change,
any client-facing column name in the response will be snake_case. If
downstream consumers depend on PascalCase keys, add response transformers
or keep quoted PascalCase columns in PG; this package recommends
updating consumers instead.

`app/api/health.py` will also work unchanged — the shape of the dict
returned by `health_check()` is `{"database_name": ..., "server_time": ...}`.

---

## 13. `docker-compose.sqlserver.yml`

Delete. Replace with `docker-compose.postgres.yml` from this package (or
commit that one into the project root).

---

## 14. `scripts/run_dev.ps1` / `run_dev.sh`

No mandatory changes. They only set up the venv and run uvicorn.
Optionally add a line to remind devs to source `.env` or to run
`run_migrations.ps1` first.

---

## 15. `README.md`

Replace the SQL Server setup sections with the Render + Postgres flow.
See `JJJ_RENDER_POSTGRES_MIGRATION_GUIDE.md` for the narrative you can
adapt.

---

## Final sanity pass

After all edits:

```powershell
python -m compileall app
uvicorn app.main:app --reload
```

Then hit the smoke-test endpoints listed in the migration guide.

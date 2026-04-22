# CHANGELOG — Render / PostgreSQL package

All changes applied when assembling this Render-ready package from the
original SQL Server / pyodbc project. Original sources are preserved under
`archive/sqlserver/` for reference.

## Added

- `render.yaml` — Render Blueprint defining the FastAPI web service and the
  managed PostgreSQL database, with `DATABASE_URL` bound via `fromDatabase`.
- `README_RENDER_DEPLOY.md` — deploy / migration / smoke-test runbook.
- `CHANGELOG_RENDER_PACKAGE.md` — this file.
- `sql/postgres/001_inventory_reservations.postgres.sql` — PG port of schema,
  constraints, and oversell trigger (`trigger_inventory_items_no_oversell`).
- `sql/postgres/002_reservation_functions.postgres.sql` — PG port of the
  three reservation stored procedures as plpgsql functions.
- `sql/postgres/003_seed_configurator_options.postgres.sql` — PG port of seed
  data, idempotent via `INSERT ... ON CONFLICT (sku) DO NOTHING`.
- `scripts/run_migrations.ps1` — PowerShell runner that applies the three
  migrations in order.
- `docker-compose.postgres.yml` — local Postgres 16 instance for development.
- `.env.render.example` — full annotated template for Render deploy.
- `reference/tables.txt` — mapping of SQL Server `dbo.PascalCase` to
  `public.snake_case` names and columns.
- `reference/MIGRATION_GUIDE.md` — guide describing the migration strategy.
- `reference/BACKEND_POSTGRES_EDIT_CHECKLIST.md` — checklist of backend code
  edits applied (for auditability).
- `reference/MIGRATION_VALIDATION_NOTES.md` — static-validation notes.

## Modified

- `app/config.py` — replaced SQL Server settings (`SQLSERVER_*`,
  `pyodbc_connection_string`) with `DATABASE_URL` plus `PG_*` fallbacks and a
  `dsn` property.
- `app/db.py` — replaced `pyodbc.connect` + ad-hoc context managers with
  `psycopg_pool.ConnectionPool` using `psycopg.rows.dict_row`. Added
  `transaction_scope` and `connection_scope` helpers.
- `app/sql_utils.py` — `quote_identifier` now emits `"..."` double-quoted
  identifiers for PostgreSQL instead of `[...]` brackets for SQL Server.
- `app/table_config.py` — all six table mappings retargeted to
  `public.snake_case` tables with snake_case PKs, `allowed_columns`,
  `searchable_columns`, and `default_order_by`.
- `app/services/crud_service.py` — rewrote queries for PG:
  - `?` → `%s` parameter placeholders
  - `CAST(col AS NVARCHAR(MAX)) LIKE` → `CAST(col AS TEXT) ILIKE`
  - `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` → `LIMIT %s OFFSET %s`
  - `INSERT/UPDATE/DELETE ... OUTPUT inserted.* / deleted.*` →
    `INSERT/UPDATE/DELETE ... RETURNING *` (single round trip, no
    `SCOPE_IDENTITY()` follow-up SELECT).
  - `dict_row` handling in fetchone (`row["total"]`).
- `app/services/reservation_service.py` — rewrote all three operations for PG:
  - `SYSUTCDATETIME()` → `now()`
  - `SELECT CAST(SCOPE_IDENTITY() AS INT)` → `INSERT ... RETURNING order_id`
  - `WITH (UPDLOCK, HOLDLOCK)` → `SELECT ... FOR UPDATE`
  - `CASE WHEN x - y < 0 THEN 0 ELSE x - y END` → `GREATEST(x - y, 0)`
  - All table references retargeted to `public.*` snake_case.
- `app/services/configurator_service.py` — rewrote configurator SELECT for PG:
  - `SELECT TOP (?)` → trailing `LIMIT %s`
  - `?` → `%s`
  - `dbo.InventoryItems` + PascalCase columns → `public.inventory_items` +
    snake_case columns
  - `IsActive = 1` → `is_active = TRUE`
  - Column aliases removed (snake_case is already the target contract).
- `requirements.txt` — removed `pyodbc==5.2.0`; added
  `psycopg[binary]==3.2.3` and `psycopg-pool==3.2.3`.
- `pyproject.toml` — description updated to mention Render/PostgreSQL/psycopg.
- `.env.example` — replaced `SQLSERVER_*` block with `DATABASE_URL` + `PG_*`
  template; original preserved at
  `archive/sqlserver/.env.sqlserver.example`.
- `.gitignore` — added `app/*.env` to prevent the legacy per-app secrets file
  from being committed.
- `README.md` — rewrote for the Render/PostgreSQL flow; pointers to
  `README_RENDER_DEPLOY.md` and `CHANGELOG_RENDER_PACKAGE.md`.

## Archived (moved to `archive/sqlserver/`)

- `sql/001_inventory_reservations.sql` (T-SQL original)
- `sql/002_reservation_procedures.sql` (T-SQL original)
- `sql/003_seed_configurator_options.sql` (T-SQL original)
- `docker-compose.sqlserver.yml`
- `app/JJJGW.env` (the local secrets file, renamed to
  `app/JJJGW.env.sample` — values scrubbed to placeholders)
- `app/test.py` (a pyodbc smoke-test script, renamed
  `app/test_sqlserver.py`)
- `app/config.py`, `app/db.py`, `app/sql_utils.py`, `app/table_config.py`,
  `app/services/crud_service.py`, `app/services/reservation_service.py`,
  `app/services/configurator_service.py` — pre-migration snapshots
- `requirements.txt`, `pyproject.toml` — pre-migration versions
- `.env.example` → `.env.sqlserver.example`
- `README.md` → `README.sqlserver.md`

## Removed from the Render copy

- `pyodbc` dependency (archived in `archive/sqlserver/requirements.txt`).
- Any real secret values: the archived `app/JJJGW.env.sample` has been
  scrubbed to placeholder text. The source project's real `app/JJJGW.env`
  file was **not** copied.
- `__pycache__/`, `*.pyc`, `.venv/`, `node_modules/` and similar caches were
  excluded during the copy.

## Not changed

- `app/main.py`, `app/schemas.py`, `app/api/*.py` — unchanged; they're
  database-agnostic and pass snake_case payloads straight through.
- `scripts/run_dev.ps1`, `scripts/run_dev.sh` — unchanged.

## Known follow-ups / TODOs

- **API PascalCase contract.** Downstream frontend consumers that previously
  relied on `InventoryItemID`, `SKU`, `QuantityOnHand`, etc. must now use
  snake_case. If you need to preserve the old contract, add column aliases in
  `app/services/crud_service.py` rather than reintroducing PascalCase
  columns.
- **`psql` not available in the build environment used to assemble this
  package**, so all SQL migration validation is static (review the files by
  eye). Run the migrations against a real Postgres once before flipping
  traffic.
- **Expire job.** The app exposes `POST /api/reservations/expire` but nothing
  calls it on a schedule. Wire a Render cron job to hit that endpoint every
  few minutes.
- **Connection-pool sizing.** `min_size=1, max_size=5` matches Render's
  Free / small Postgres connection limit. Bump these in `app/db.py` if you
  scale up the database plan.
- **Render Postgres database plan.** `render.yaml` uses `plan: free` for the
  database. Render's legacy Postgres plans (such as `starter`) are no longer
  valid for new databases — pick `free` for dev or a current paid tier
  (e.g. `basic-256mb`, `basic-1gb`, `pro-*`) for production.
- **CORS_ORIGINS parsing fix.** pydantic-settings v2 JSON-decodes env vars
  typed as `list[str]` before any validator runs, so a comma-separated
  `CORS_ORIGINS` (the Render-friendly form) raised
  `SettingsError: error parsing value for field "cors_origins"`. The
  field is now stored as a raw string (`cors_origins_raw`) and the parsed
  list is exposed via a `@computed_field` property on `Settings`. The
  property accepts comma-separated, single URL, JSON list literal, and
  empty/unset values. `app/main.py` already passes `settings.cors_origins`
  to `CORSMiddleware`, so no call-site changes were needed. See
  `CORS_SETTINGS_FIX.md`.
- **Python runtime pinned to 3.12.8.** Render was otherwise defaulting to
  Python 3.14, for which `pydantic-core` ships no manylinux wheel. pip then
  tried to build `pydantic-core` from source with `maturin`/`cargo`, which
  fails on Render's read-only cargo registry. The pin is applied via
  `render.yaml` (`PYTHON_VERSION=3.12.8`), `.python-version`, and
  `runtime.txt`. `requirements.txt` also pins `pydantic-core==2.27.2` (has
  a cp312 manylinux wheel) and `pyproject.toml` narrows to
  `requires-python = ">=3.11,<3.13"`. Build command switched to
  `pip install --only-binary=:all: -r requirements.txt` so any future
  wheel-less resolution fails fast instead of invoking cargo.
  See `BUILD_FIX_PYTHON_VERSION.md`.

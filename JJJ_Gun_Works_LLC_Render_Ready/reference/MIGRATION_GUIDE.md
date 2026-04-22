# JJJ Gun Works LLC — Render PostgreSQL Migration Guide

This guide is tailored to the FastAPI backend at
`JJJ_Gun_Works_LLC_extracted/JJJ Gun Works LLC`. It walks through switching
from local SQL Server + `pyodbc` to Render-managed PostgreSQL + `psycopg` 3,
including PowerShell commands, file-by-file backend edits, and how to apply
the three PostgreSQL scripts in `sql/` of this package.

Nothing in this guide modifies the original extracted project — all edits
are shown as patches you apply to your own working copy.

---

## 0. What's in this package

```
jjj_render_postgres_migration_package/
├── JJJ_RENDER_POSTGRES_MIGRATION_GUIDE.md     ← you are here
├── BACKEND_POSTGRES_EDIT_CHECKLIST.md          ← exact Python edits
├── VALIDATION_NOTES.md                         ← what was / wasn't validated
├── .env.render.example                         ← DATABASE_URL template
├── docker-compose.postgres.yml                 ← local Postgres 16
├── migration/
│   └── tables.txt                              ← SQL Server → PG mapping
├── scripts/
│   └── run_migrations.ps1                      ← applies the three SQL files
└── sql/
    ├── 001_inventory_reservations.postgres.sql     ← tables, indexes, triggers
    ├── 002_reservation_functions.postgres.sql      ← plpgsql functions
    └── 003_seed_configurator_options.postgres.sql  ← seed via ON CONFLICT
```

---

## 1. Prerequisites

- **Render account** with permission to create a Postgres instance and a
  web service.
- **PostgreSQL client tools** installed locally (`psql`). On Windows, install
  the official PostgreSQL installer and ensure `C:\Program Files\PostgreSQL\<ver>\bin`
  is on your `PATH`.
- **Docker Desktop** (only for local parity testing).
- **Python 3.11+** and a fresh virtualenv.

Quick PowerShell check:

```powershell
psql --version
docker --version
python --version
```

---

## 2. Create the Render Postgres instance

1. In the Render dashboard: **New → PostgreSQL**. Choose the same region
   you plan to deploy the web service in.
2. Pick an instance size (Starter is fine for dev). Name it
   `jjj-firearms-postgres`.
3. After provisioning, copy:
   - **Internal Database URL** — used by the Render web service.
   - **External Database URL** — used from your laptop to run migrations.

Both URLs already include `?sslmode=require`. Render-managed PG accepts
only TLS connections; `psycopg` will honor that automatically.

---

## 3. Apply the three SQL migrations from your laptop

The SQL files in `sql/` are idempotent — applying them to a fresh or
partially-migrated database is safe.

### 3a. Option A — using the helper script (recommended)

```powershell
# From the migration package root:
cd C:\path\to\jjj_render_postgres_migration_package

$env:DATABASE_URL = "postgresql://<user>:<password>@<host>:5432/<database>?sslmode=require"

.\scripts\run_migrations.ps1
```

Flags:

- `-SkipSeed` — skip `003_seed_configurator_options.postgres.sql`.
- `-SkipFunctions` — skip `002_reservation_functions.postgres.sql` (the
  backend implements the same logic inline, so 002 is optional).
- `-DatabaseUrl "<url>"` — pass the URL instead of relying on `$env:DATABASE_URL`.

### 3b. Option B — straight `psql`

```powershell
$env:PGOPTIONS = "-c statement_timeout=60000"

psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f sql\001_inventory_reservations.postgres.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f sql\002_reservation_functions.postgres.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f sql\003_seed_configurator_options.postgres.sql
```

Verify:

```powershell
psql "$env:DATABASE_URL" -c "\dt public.*"
psql "$env:DATABASE_URL" -c "SELECT COUNT(*) FROM public.inventory_items;"
```

Expect 6 tables and 15 seeded inventory rows.

---

## 4. Local parity — run the same migrations against a Docker Postgres

From the migration package root:

```powershell
docker compose -f .\docker-compose.postgres.yml up -d

$env:DATABASE_URL = "postgresql://firearms_app:dev_password_change_me@localhost:5432/firearms_inventory?sslmode=disable"
.\scripts\run_migrations.ps1
```

Stop and wipe when you're done:

```powershell
docker compose -f .\docker-compose.postgres.yml down -v
```

---

## 5. Backend edits — summary

Full details live in `BACKEND_POSTGRES_EDIT_CHECKLIST.md`. The high-level
changes, in the order you should apply them to your working copy of
`JJJ_Gun_Works_LLC_extracted/JJJ Gun Works LLC`:

| File | What changes |
| --- | --- |
| `requirements.txt` | Remove `pyodbc==5.2.0`; add `psycopg[binary]==3.2.3` and `psycopg-pool==3.2.3`. |
| `.env.example` | Replace SQL Server vars with `DATABASE_URL` and optional `PG_*` fallbacks (see `.env.render.example`). |
| `app/JJJGW.env` | **Delete** the file. It's a stray SQL Server env file and not consumed by current `Settings`. |
| `app/config.py` | Drop every `sqlserver_*` field and `odbc_connection_string`. Add `database_url`, `pg_*` fields, and a `dsn` property. |
| `app/db.py` | Replace `import pyodbc` with `import psycopg`. Rewrite `get_connection`, `connection_scope`, `transaction_scope`, `rows_to_dicts`, `execute_*`, `health_check`. |
| `app/sql_utils.py` | Change `quote_identifier` to double-quote style. |
| `app/table_config.py` | `schema="dbo"` → `schema="public"`; rename tables and columns to `snake_case` (see `migration/tables.txt`). |
| `app/services/crud_service.py` | `?` → `%s`; `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` → `LIMIT %s OFFSET %s`; `CAST(col AS NVARCHAR(MAX)) LIKE ?` → `CAST(col AS TEXT) ILIKE %s`; replace `SCOPE_IDENTITY()` with `INSERT ... RETURNING <pk>`. |
| `app/services/reservation_service.py` | `?` → `%s`; drop `WITH (UPDLOCK, HOLDLOCK)`; `SYSUTCDATETIME()` → `now()`; replace `SCOPE_IDENTITY()` with `RETURNING`. |
| `app/services/configurator_service.py` | `SELECT TOP (?)` → `SELECT ... LIMIT %s`; swap `?` for `%s`; move `limit` to last bound param. |
| `docker-compose.sqlserver.yml` | **Delete**. Replaced by `docker-compose.postgres.yml` in this package. |
| `README.md` | Replace the SQL Server sections with the Render PG flow described here. |

---

## 6. Deploy the FastAPI backend to Render

This project has no `render.yaml` yet. Create one at the repo root:

```yaml
services:
  - type: web
    name: jjj-firearms-api
    env: python
    region: oregon            # must match the Postgres region
    plan: starter
    buildCommand: "pip install --upgrade pip && pip install -r requirements.txt"
    startCommand: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: jjj-firearms-postgres
          property: connectionString
      - key: APP_ENV
        value: production
      - key: API_PREFIX
        value: /api
      - key: CORS_ORIGINS
        value: "https://your-frontend-host"
```

One-off migration hook: in the Render dashboard, add a **Job** that runs
`psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/001_inventory_reservations.postgres.sql -f sql/002_reservation_functions.postgres.sql -f sql/003_seed_configurator_options.postgres.sql`,
or keep running `run_migrations.ps1` from your laptop using the External URL.

---

## 7. Smoke test checklist

After migrations and first deploy:

- `GET /api/health` — should return `{"status": "ok", "database_name": "<render db>", "server_time": "..."}`.
- `GET /api/inventory/tables` — lists the four mapped inventory tables.
- `GET /api/inventory/items?page=1&page_size=5` — returns seeded rows.
- `GET /api/configurator/rifle/options` — returns 5 options per group
  from the seed data.
- `POST /api/reservations` with a known `inventory_item_id` — creates a
  reservation; verify `quantity_reserved` ticked up.
- `POST /api/reservations/release` — verify `quantity_reserved` ticks back
  down.
- Attempt to over-reserve an item (request `quantity` > available). The
  API must return `409 Conflict` and the DB `inventory_items` row must be
  unchanged. This validates both the guarded UPDATE in the backend and
  the `inventory_items_no_oversell` trigger.

---

## 8. Rollback

The migration scripts are forward-only, but everything they create lives
in the `public` schema and is drop-safe:

```powershell
psql "$env:DATABASE_URL" -c "DROP TABLE IF EXISTS public.order_reservations, public.orders, public.stock_movements, public.inventory_items, public.suppliers, public.part_categories CASCADE;"
psql "$env:DATABASE_URL" -c "DROP FUNCTION IF EXISTS public.usp_create_order_reservation(int,int,int,timestamptz), public.usp_release_reservation(int), public.usp_expire_reservations(timestamptz);"
psql "$env:DATABASE_URL" -c "DROP FUNCTION IF EXISTS public.trg_inventory_items_no_oversell() CASCADE;"
psql "$env:DATABASE_URL" -c "DROP FUNCTION IF EXISTS public.trg_order_reservations_status_integrity() CASCADE;"
```

For a cleaner rollback, provision a new empty Render Postgres and cut over.

---

## 9. Common pitfalls

- **`sslmode=require` missing on local dev** — the Render URL has it;
  Docker's local PG does not accept TLS out-of-the-box. Use
  `sslmode=disable` locally and `sslmode=require` on Render.
- **Hardcoded `dbo.` references** in SQL strings inside `reservation_service.py`
  and `configurator_service.py` — change to `public.` (or remove the
  schema qualifier entirely if `search_path` is already `public`).
- **Mixed-case column names in raw SQL** — once `app/table_config.py`
  moves to snake_case, make sure every raw SQL string uses the new names
  too. The checklist enumerates each location.
- **Pydantic parsing of identity types** — `INT GENERATED ALWAYS AS IDENTITY`
  still exposes integer PKs; the existing Pydantic models are fine.
- **`email_validator`** is already in `requirements.txt` and still required
  (Pydantic `EmailStr`).
- **`psycopg` row factories** — by default psycopg returns tuples. Use
  `conn.cursor(row_factory=dict_row)` (import from `psycopg.rows`) or keep
  the existing `rows_to_dicts` helper (also shown in the checklist).

---

## 10. Where to go next

- `BACKEND_POSTGRES_EDIT_CHECKLIST.md` — concrete Python edits, copy-pasteable.
- `migration/tables.txt` — the full per-column mapping.
- `sql/*.postgres.sql` — the three PG migration scripts.
- `VALIDATION_NOTES.md` — what was validated statically and what still
  needs a real DB to verify.

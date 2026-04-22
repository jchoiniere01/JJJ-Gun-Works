# Validation Notes

## Environment at time of authoring

- No PostgreSQL server or `psql` client is available in the environment
  where this package was assembled (`psql --version` failed; `postgres`
  binary not on PATH).
- Therefore every SQL file in this package has been **statically reviewed
  only** — nothing has been executed against a live PostgreSQL instance.

## What was checked statically

1. **Syntax shape** of every CREATE statement matches PostgreSQL 15/16
   reference grammar:
   - `CREATE TABLE IF NOT EXISTS schema.name (...)` with inline
     `PRIMARY KEY`, `DEFAULT`, `CHECK`, `FOREIGN KEY`.
   - `CREATE INDEX IF NOT EXISTS ... INCLUDE (...)` — supported since
     PostgreSQL 11.
   - `CREATE OR REPLACE FUNCTION ... LANGUAGE plpgsql AS $$ ... $$;`
     with proper `RETURNS trigger` / `RETURNS TABLE(...)` shapes.
   - Trigger definition uses `BEFORE INSERT OR UPDATE ... FOR EACH ROW
     EXECUTE FUNCTION` (PostgreSQL 11+ preferred form).

2. **Data type choices** cross-checked against the SQL Server source:
   - `NVARCHAR(n)` → `VARCHAR(n)` / `NVARCHAR(MAX)` → `TEXT`.
   - `BIT` → `BOOLEAN` with matching TRUE/FALSE defaults.
   - `DATETIME2(3)` → `TIMESTAMPTZ` (the app uses UTC timestamps; PG
     stores TIMESTAMPTZ in UTC internally).
   - `INT IDENTITY(1,1)` → `INT GENERATED ALWAYS AS IDENTITY`.
   - `DECIMAL(19,4)` → `NUMERIC(19,4)` (functionally identical).

3. **Check constraint preservation** — both `CK_InventoryItems_Quantities`
   and `CK_OrderReservations_Status` translate verbatim; no semantic
   change.

4. **Trigger semantics**:
   - SQL Server AFTER INSERT/UPDATE triggers read the `inserted` pseudo-
     table and `THROW` to abort.
   - The PG equivalents are BEFORE INSERT OR UPDATE row-level triggers
     that inspect `NEW` and `RAISE EXCEPTION`. Using BEFORE is safe here
     because both triggers only validate the row; they don't re-query
     other rows, so there's no set-based nuance to worry about.

5. **Stored procedure → function translation**:
   - T-SQL `@@ROWCOUNT` → plpgsql `GET DIAGNOSTICS v_rowcount = ROW_COUNT;`
   - T-SQL `SCOPE_IDENTITY()` → `INSERT ... RETURNING <pk>`.
   - T-SQL table variable `@Expired` replaced with `CREATE TEMP TABLE ...
     ON COMMIT DROP` inside the function. This matches set-based
     semantics and works when called within a transaction (which PG
     wraps around function calls by default).
   - T-SQL `BEGIN TRANSACTION / COMMIT / ROLLBACK / SET XACT_ABORT ON`
     removed. Plpgsql functions execute inside an enclosing transaction;
     raising an exception rolls back.
   - `WITH (UPDLOCK, HOLDLOCK)` hints on SELECTs translated to
     `SELECT ... FOR UPDATE`. Hints on UPDATEs were dropped — PG's
     UPDATE already takes the appropriate row lock for the matched rows.

6. **Seed data**:
   - T-SQL `MERGE ... WHEN NOT MATCHED THEN INSERT` replaced with
     `INSERT ... ON CONFLICT (sku) DO NOTHING`. Behaviorally equivalent
     for the insert-once use case.
   - `SELECT TOP 1 CategoryID ...` replaced with scalar subquery +
     `LIMIT 1`.
   - Single quote escaping (`Spike''s Tactical`) preserved in PG form.

7. **Python code** was NOT modified in place. All backend edits are
   described as patches in `BACKEND_POSTGRES_EDIT_CHECKLIST.md` and
   have been spot-checked against the current file contents of:
   - `app/db.py`
   - `app/config.py`
   - `app/sql_utils.py`
   - `app/table_config.py`
   - `app/services/crud_service.py`
   - `app/services/reservation_service.py`
   - `app/services/configurator_service.py`
   These patches are syntactically plausible but have not been executed.

## What was NOT validated

The following require a real PostgreSQL instance and a running backend:

- Actually applying `001_*`, `002_*`, `003_*` via `psql` and observing
  no errors.
- Verifying the `INCLUDE (...)` covering-index clause is accepted by the
  target server version.
- Verifying the `CREATE TEMP TABLE ... ON COMMIT DROP` behavior inside
  `usp_expire_reservations` when called from psql (it requires the call
  to happen inside a transaction — psql wraps each `SELECT`-of-function
  in an implicit transaction, which is sufficient).
- Verifying FastAPI request/response roundtrips with real `psycopg`
  connection pooling.
- Verifying Render's Postgres TLS (`sslmode=require`) with `psycopg` 3
  from a Render web service.
- Performance characteristics of the guarded UPDATE under concurrent
  load — the logic is identical to the SQL Server version, but Render's
  instance size will dictate real throughput.

## Recommended validation steps before production

1. Run `docker compose -f docker-compose.postgres.yml up -d`.
2. Run `scripts/run_migrations.ps1`. Confirm it exits 0.
3. Run the `SELECT`-based smoke checks from the guide.
4. Bring up the patched FastAPI backend locally and run the API smoke
   tests in section 7 of the guide.
5. Provision Render Postgres and repeat steps 2–4 against the External
   URL, then deploy the web service.

If any SQL in `sql/*.postgres.sql` fails during step 2, the most likely
causes are:

- `INCLUDE (...)` unsupported — the target server is older than PG 11.
  Fix by removing the `INCLUDE (...)` clause.
- `GENERATED ALWAYS AS IDENTITY` unsupported — only on PG < 10. Replace
  with `SERIAL` / `BIGSERIAL`.
- Insufficient privileges to create functions in `public`. Grant
  `CREATE ON SCHEMA public` to the migration user, or run as the
  database owner.

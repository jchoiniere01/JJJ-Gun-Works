# Firearms Inventory FastAPI Backend — Render / PostgreSQL edition

FastAPI backend for firearms inventory and AR configurator, packaged for deploy
on Render with a managed PostgreSQL 16 database.

Features:

- PostgreSQL connection through `psycopg` 3 + `psycopg_pool.ConnectionPool`
- CRUD endpoints for inventory tables
- Order reservation endpoints with transactional oversell protection
  (guarded UPDATE + `FOR UPDATE` row locks)
- Database-level backstop via plpgsql BEFORE INSERT/UPDATE triggers and helper
  functions (see `sql/postgres/`)
- AR rifle/pistol configurator API returning options for lower receiver, riser
  mount, and pistol grip
- Optional seed data for local testing

See `README_RENDER_DEPLOY.md` for upload/deploy/migration/smoke-test steps on
Render, and `CHANGELOG_RENDER_PACKAGE.md` for what changed vs. the original
SQL Server build (archived under `archive/sqlserver/`).

## Project structure

```text
app/
  api/
    configurator.py
    health.py
    inventory.py
    orders.py
    reservations.py
  services/
    configurator_service.py
    crud_service.py
    reservation_service.py
  config.py
  db.py
  main.py
  schemas.py
  sql_utils.py
  table_config.py
sql/
  postgres/
    001_inventory_reservations.postgres.sql
    002_reservation_functions.postgres.sql
    003_seed_configurator_options.postgres.sql
scripts/
  run_dev.ps1
  run_dev.sh
  run_migrations.ps1
archive/
  sqlserver/           # original SQL Server assets preserved for reference
reference/
  tables.txt
  MIGRATION_GUIDE.md
  BACKEND_POSTGRES_EDIT_CHECKLIST.md
  MIGRATION_VALIDATION_NOTES.md
render.yaml
docker-compose.postgres.yml
.env.example
.env.render.example
```

## PostgreSQL schema

The migration scripts create these tables in `public`:

- `public.inventory_items`
- `public.part_categories`
- `public.suppliers`
- `public.stock_movements`
- `public.orders`
- `public.order_reservations`

Columns use `snake_case`. If you need to preserve the legacy PascalCase API
contract for existing frontends, add column aliases in
`app/services/crud_service.py` rather than reintroducing mixed-case identifiers
in `app/table_config.py`.

The configurator reads from `public.inventory_items` using these columns:

- `inventory_item_id`, `sku`, `name`, `manufacturer`, `model`, `caliber`,
  `platform`, `part_role`, `build_type`, `unit_price`, `quantity_on_hand`,
  `quantity_reserved`, `is_active`

Part roles are normalized by query:

- `lower receiver`, `lower_receiver`, `lower`
- `riser mount`, `riser_mount`, `riser`
- `pistol grip`, `pistol_grip`, `grip`

## Local development

### Option A — Docker Compose (recommended)

```bash
docker compose -f docker-compose.postgres.yml up -d
cp .env.example .env
# edit .env and set DATABASE_URL to the local compose instance, e.g.
# DATABASE_URL=postgresql://firearms_app:<password>@localhost:5432/firearms_inventory
```

Apply migrations (psql):

```bash
psql "$DATABASE_URL" -f sql/postgres/001_inventory_reservations.postgres.sql
psql "$DATABASE_URL" -f sql/postgres/002_reservation_functions.postgres.sql
psql "$DATABASE_URL" -f sql/postgres/003_seed_configurator_options.postgres.sql
```

Windows alternative: `scripts/run_migrations.ps1`.

Run the API:

```bash
./scripts/run_dev.sh
# or
uvicorn app.main:app --reload
```

### Option B — Render managed Postgres (production)

See `README_RENDER_DEPLOY.md`.

## Endpoint summary

### Health

```http
GET /api/health
```

### Inventory CRUD

```http
GET  /api/inventory/tables
GET  /api/inventory/items?page=1&page_size=50&q=lower
GET  /api/inventory/categories
GET  /api/inventory/suppliers
GET  /api/inventory/stock_movements
GET  /api/inventory/items/1
POST /api/inventory/items
PATCH /api/inventory/items/1
DELETE /api/inventory/items/1
```

Column-equality filters use snake_case keys:

```http
GET /api/inventory/items?part_role=lower%20receiver&build_type=rifle
```

Create payload (snake_case):

```json
{
  "data": {
    "sku": "LR-100",
    "name": "Sample AR Lower Receiver",
    "part_role": "lower receiver",
    "build_type": "both",
    "quantity_on_hand": 5,
    "quantity_reserved": 0,
    "is_active": true,
    "requires_ffl": true,
    "is_serialized": true
  }
}
```

### Orders / reservations

```http
GET  /api/orders/tables
GET  /api/orders/orders
GET  /api/orders/reservations
POST /api/reservations
POST /api/reservations/release
POST /api/reservations/expire
```

`POST /api/reservations` body:

```json
{
  "order": {
    "customer_name": "Test Customer",
    "customer_email": "customer@example.com",
    "customer_phone": "555-0100",
    "build_type": "rifle",
    "notes": "Demo rifle build"
  },
  "lines": [
    {"inventory_item_id": 1, "quantity": 1},
    {"inventory_item_id": 6, "quantity": 1},
    {"inventory_item_id": 11, "quantity": 1}
  ],
  "expires_at": "2026-04-22T18:00:00Z"
}
```

If any line cannot be reserved, the transaction rolls back and returns
`409 Conflict`.

### Configurator

```http
GET /api/configurator/rifle/options
GET /api/configurator/pistol/options
GET /api/configurator/rifle/parts/lower_receiver?limit=5
```

## Oversell protection design

Each reservation line runs inside one transaction as a guarded UPDATE:

```sql
UPDATE public.inventory_items
   SET quantity_reserved = quantity_reserved + %s,
       updated_at        = now()
 WHERE inventory_item_id = %s
   AND is_active = TRUE
   AND quantity_on_hand - quantity_reserved >= %s;
```

If `cursor.rowcount == 0` the API raises `409 Conflict` and rolls back the
whole order. PostgreSQL takes a row-level lock on every matched row inside the
UPDATE, so concurrent requests cannot double-reserve the same stock.

Database-level backstops created by the migrations:

- `CHECK (quantity_on_hand >= 0 AND quantity_reserved >= 0
   AND quantity_reserved <= quantity_on_hand)`
- `trigger_inventory_items_no_oversell` (BEFORE INSERT/UPDATE, plpgsql)
- Helper functions: `create_order_reservation`, `release_reservation`,
  `expire_reservations`

## Notes for firearms compliance

This backend tracks inventory and build configuration data only. It does not
replace bound book, ATF recordkeeping, background check, serialization,
acquisition/disposition, or state-specific compliance workflows. For production
use, add compliance-specific audit tables, immutable logs, user permissions,
and record retention policy.

## Development checks

```bash
python -m compileall app
uvicorn app.main:app --reload
```

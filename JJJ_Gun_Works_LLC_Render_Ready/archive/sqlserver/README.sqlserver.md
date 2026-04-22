# Firearms Inventory FastAPI Backend

Complete FastAPI backend for a local SQL Server firearms inventory and AR configurator database.

It includes:

- SQL Server connection through `pyodbc`
- CRUD endpoints for mapped inventory tables
- Order reservation endpoints with transaction-level oversell protection
- SQL Server triggers and stored procedures as database-level oversell protection
- Dynamic AR rifle/pistol configurator API returning five available options for:
  - lower receiver
  - riser mount
  - pistol grip
- Optional seed data for local testing

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
  001_inventory_reservations.sql
  002_reservation_procedures.sql
  003_seed_configurator_options.sql
scripts/
  run_dev.ps1
  run_dev.sh
```

## Assumed SQL Server schema

The default table mappings expect these converted T-SQL tables:

- `dbo.InventoryItems`
- `dbo.PartCategories`
- `dbo.Suppliers`
- `dbo.StockMovements`
- `dbo.Orders`
- `dbo.OrderReservations`

If your converted schema uses different names, update `app/table_config.py`.

The configurator expects `dbo.InventoryItems` to expose these columns:

- `InventoryItemID`
- `SKU`
- `Name`
- `Manufacturer`
- `Model`
- `Caliber`
- `Platform`
- `PartRole`
- `BuildType`
- `UnitPrice`
- `QuantityOnHand`
- `QuantityReserved`
- `IsActive`

The part roles are normalized by query to accept:

- `lower receiver`, `lower_receiver`, `lower`
- `riser mount`, `riser_mount`, `riser`
- `pistol grip`, `pistol_grip`, `grip`

## Setup on Windows with local SQL Server

1. Install the Microsoft ODBC driver for SQL Server.

   Recommended: `ODBC Driver 18 for SQL Server`

2. Create and configure your environment file.

   ```powershell
   Copy-Item .env.example .env
   ```

3. Edit `.env`.

   SQL Server Express example:

   ```text
   SQLSERVER_DRIVER=ODBC Driver 18 for SQL Server
   SQLSERVER_SERVER=localhost\SQLEXPRESS
   SQLSERVER_DATABASE=FirearmsInventory
   SQLSERVER_TRUSTED_CONNECTION=true
   SQLSERVER_ENCRYPT=no
   SQLSERVER_TRUST_SERVER_CERTIFICATE=yes
   ```

   SQL authentication example:

   ```text
   SQLSERVER_TRUSTED_CONNECTION=false
   SQLSERVER_USERNAME=sa
   SQLSERVER_PASSWORD=your-password
   ```

4. Run the SQL scripts in SQL Server Management Studio or Azure Data Studio.

   Run in order:

   ```text
   sql/001_inventory_reservations.sql
   sql/002_reservation_procedures.sql
   sql/003_seed_configurator_options.sql
   ```

   The third script is optional seed data.

5. Start the API.

   ```powershell
   .\scripts\run_dev.ps1
   ```

6. Open the API docs.

   ```text
   http://127.0.0.1:8000/docs
   ```

## Setup on macOS/Linux

Install the SQL Server ODBC driver for your platform, then:

```bash
cp .env.example .env
chmod +x scripts/run_dev.sh
./scripts/run_dev.sh
```

## Endpoint summary

### Health

```http
GET /api/health
```

### Inventory CRUD

List mapped tables:

```http
GET /api/inventory/tables
```

List rows:

```http
GET /api/inventory/items?page=1&page_size=50&q=lower
GET /api/inventory/categories
GET /api/inventory/suppliers
GET /api/inventory/stock_movements
```

Filter using any mapped column:

```http
GET /api/inventory/items?PartRole=lower receiver&BuildType=rifle
```

Get one row:

```http
GET /api/inventory/items/1
```

Create:

```http
POST /api/inventory/items
Content-Type: application/json

{
  "data": {
    "SKU": "LR-100",
    "Name": "Sample AR Lower Receiver",
    "PartRole": "lower receiver",
    "BuildType": "both",
    "QuantityOnHand": 5,
    "QuantityReserved": 0,
    "IsActive": true,
    "RequiresFFL": true,
    "IsSerialized": true
  }
}
```

Update:

```http
PATCH /api/inventory/items/1
Content-Type: application/json

{
  "data": {
    "QuantityOnHand": 10,
    "UnitPrice": 129.99
  }
}
```

Delete:

```http
DELETE /api/inventory/items/1
```

### Order table CRUD

```http
GET /api/orders/tables
GET /api/orders/orders
GET /api/orders/reservations
```

### Create reservation

```http
POST /api/reservations
Content-Type: application/json

{
  "order": {
    "customer_name": "Test Customer",
    "customer_email": "customer@example.com",
    "customer_phone": "555-0100",
    "build_type": "rifle",
    "notes": "Demo rifle build"
  },
  "lines": [
    {
      "inventory_item_id": 1,
      "quantity": 1
    },
    {
      "inventory_item_id": 6,
      "quantity": 1
    },
    {
      "inventory_item_id": 11,
      "quantity": 1
    }
  ],
  "expires_at": "2026-04-22T18:00:00Z"
}
```

If any line cannot be reserved, the transaction rolls back and returns `409 Conflict`.

### Release reservations

Release by order:

```http
POST /api/reservations/release
Content-Type: application/json

{
  "order_id": 1
}
```

Release specific reservations:

```http
POST /api/reservations/release
Content-Type: application/json

{
  "reservation_ids": [1, 2, 3]
}
```

### Expire reservations

```http
POST /api/reservations/expire
```

Optional cutoff:

```http
POST /api/reservations/expire?as_of=2026-04-22T18:00:00Z
```

### Configurator

Return five options for each required group:

```http
GET /api/configurator/rifle/options
GET /api/configurator/pistol/options
```

Return one group:

```http
GET /api/configurator/rifle/parts/lower_receiver?limit=5
GET /api/configurator/rifle/parts/riser_mount?limit=5
GET /api/configurator/rifle/parts/pistol_grip?limit=5
```

## Oversell protection design

The main reservation path uses one SQL Server transaction.

For each requested item it runs a guarded update:

```sql
UPDATE dbo.InventoryItems WITH (UPDLOCK, HOLDLOCK)
SET QuantityReserved = QuantityReserved + @RequestedQuantity
WHERE InventoryItemID = @InventoryItemID
  AND IsActive = 1
  AND QuantityOnHand - QuantityReserved >= @RequestedQuantity;
```

If `@@ROWCOUNT` is zero, the API raises `409 Conflict` and rolls back the whole order.

The database also includes:

- `CK_InventoryItems_Quantities`
- `dbo.trg_InventoryItems_NoOversell`
- `dbo.usp_CreateOrderReservation`
- `dbo.usp_ReleaseReservation`
- `dbo.usp_ExpireReservations`

That gives you protection for API writes, direct SQL writes, and future non-API clients.

## Notes for firearms compliance

This backend tracks inventory and build configuration data only. It does not replace bound book, ATF recordkeeping, background check, serialization, acquisition/disposition, or state-specific compliance workflows. For production use, add your compliance-specific audit tables, immutable logs, user permissions, and record retention policy.

## Common customization points

### Table names and columns

Edit:

```text
app/table_config.py
```

### Configurator matching

Edit:

```text
app/services/configurator_service.py
```

### Reservation business logic

Edit:

```text
app/services/reservation_service.py
```

## Development checks

Compile Python files:

```bash
python -m compileall app
```

Run API:

```bash
uvicorn app.main:app --reload
```

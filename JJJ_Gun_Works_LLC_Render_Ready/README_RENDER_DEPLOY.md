# Deploying to Render

This package is pre-wired to deploy on Render with a managed PostgreSQL 16
instance and a Python web service running FastAPI/uvicorn.

## 1. Prerequisites

- A [Render](https://render.com) account
- `psql` available locally (or use Render's "Connect" shell) to run migrations
- The source for this package (zip or git repo)

## 2. Upload / connect the repo

Option A — Git (recommended):

1. Push this folder to a GitHub/GitLab/Bitbucket repo.
2. In Render, choose **New → Blueprint** and point it at the repo.
   `render.yaml` will be detected and will create both the web service and
   the Postgres database in one step.

Option B — Manual:

1. Create **New → PostgreSQL** using the settings in `render.yaml`
   (database name `firearms_inventory`, user `firearms_app`, plan `starter`).
2. Create **New → Web Service** pointing at the repo, with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. On the web service, add an environment variable `DATABASE_URL` whose value
   is the managed Postgres **Internal Database URL** (already includes
   `?sslmode=require`).

## 3. Run migrations (once, before the web service makes its first query)

Copy the **External Database URL** from the Render Postgres dashboard, then
from your laptop:

```bash
export DATABASE_URL="postgresql://<user>:<password>@<host>:5432/<database>?sslmode=require"
psql "$DATABASE_URL" -f sql/postgres/001_inventory_reservations.postgres.sql
psql "$DATABASE_URL" -f sql/postgres/002_reservation_functions.postgres.sql
psql "$DATABASE_URL" -f sql/postgres/003_seed_configurator_options.postgres.sql
```

Windows (PowerShell):

```powershell
$env:DATABASE_URL = "postgresql://<user>:<password>@<host>:5432/<database>?sslmode=require"
.\scripts\run_migrations.ps1
```

The third script is optional seed data for the configurator.

## 4. Environment variables

| Variable | Source | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Render managed Postgres (`fromDatabase` binding) | Takes precedence over `PG_*` |
| `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASSWORD`, `PG_SSLMODE`, `PG_TIMEOUT_SECONDS` | Optional fallbacks | Only used if `DATABASE_URL` is empty |
| `APP_NAME` | static | `Firearms Inventory API` |
| `APP_ENV` | static | `production` on Render, `local` for dev |
| `API_PREFIX` | static | `/api` |
| `CORS_ORIGINS` | static | Comma-separated list of allowed origins |

The real secrets (passwords, connection strings) live only in Render's
encrypted environment variables. Do **not** commit `.env`. Use
`.env.example` / `.env.render.example` as templates.

## 5. Smoke test

Once the service is live at `https://<service>.onrender.com`:

```bash
curl https://<service>.onrender.com/api/health
```

Expected response:

```json
{
  "status": "ok",
  "database_name": "firearms_inventory",
  "server_time": "2026-04-22T..."
}
```

Additional smoke checks:

```bash
curl "https://<service>.onrender.com/api/inventory/tables"
curl "https://<service>.onrender.com/api/configurator/rifle/options"
```

If the seed script ran, the configurator call should return five options per
part group.

## 6. Reservation round-trip test

```bash
curl -X POST "https://<service>.onrender.com/api/reservations" \
  -H "Content-Type: application/json" \
  -d '{
        "order": {"customer_name": "Smoke Test", "build_type": "rifle"},
        "lines": [{"inventory_item_id": 1, "quantity": 1}],
        "expires_at": "2026-04-22T23:59:00Z"
      }'
```

Then release:

```bash
curl -X POST "https://<service>.onrender.com/api/reservations/release" \
  -H "Content-Type: application/json" \
  -d '{"order_id": <order_id_from_previous_response>}'
```

## 7. Troubleshooting

- **`psycopg.OperationalError: SSL required`** — your `DATABASE_URL` is
  missing `?sslmode=require`. Render's managed URLs already include it; if you
  copied one without, append it.
- **`relation "public.inventory_items" does not exist`** — migrations did not
  run. Re-run step 3 against the external URL.
- **Web service crashes on boot with `ModuleNotFoundError: psycopg`** —
  confirm `requirements.txt` ships `psycopg[binary]==3.2.3` (the binary extra
  is required for Render's Python image because it ships no libpq).
- **`409 Conflict` on every reservation** — inventory is seeded with zero
  quantities or the guarded UPDATE's `is_active = TRUE` + availability check
  is failing. Inspect `public.inventory_items` directly.
- **Low connection limit on Starter plan** — the app uses a small pool
  (`min_size=1`, `max_size=5`). Bump in `app/db.py` when you upgrade the
  Postgres plan.

## 8. Post-deploy hardening (optional)

- Add a Render cron job that calls `POST /api/reservations/expire` on a
  schedule (e.g. every 5 minutes).
- Enable Render's automatic daily Postgres backups.
- Restrict `CORS_ORIGINS` to the production frontend hostnames.
- Rotate the database password via the Render dashboard if it was ever
  exposed.

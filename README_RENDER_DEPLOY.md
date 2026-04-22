# Deploying to Render

This package is pre-wired to deploy on Render with a managed PostgreSQL 16
instance and a Python web service running FastAPI/uvicorn.

## 1. Prerequisites

- A [Render](https://render.com) account
- `psql` available locally (or use Render's "Connect" shell) to run migrations
- The source for this package (zip or git repo)

### Python version

This package pins **Python 3.12.8** via three mechanisms so Render never
defaults to the latest interpreter:

- `render.yaml` sets `PYTHON_VERSION=3.12.8` in the web service `envVars`
- `.python-version` at the repo root (`3.12.8`)
- `runtime.txt` at the repo root (`python-3.12.8`)

Do not remove any of these without verifying that every pinned dependency
ships a prebuilt manylinux wheel for the new interpreter. See
`BUILD_FIX_PYTHON_VERSION.md` for why — a Python 3.14 default would force
`pydantic-core` to build from source via `maturin`/`cargo`, which fails on
Render's read-only cargo registry.

## 2. Upload / connect the repo

Option A — Git (recommended):

1. Push this folder to a GitHub/GitLab/Bitbucket repo.
2. In Render, choose **New → Blueprint** and point it at the repo.
   `render.yaml` will be detected and will create both the web service and
   the Postgres database in one step.

Option B — Manual:

1. Create **New → PostgreSQL** using the settings in `render.yaml`
   (database name `firearms_inventory`, user `firearms_app`, plan `free`).
   Note: Render's legacy Postgres plans such as `starter` are no longer
   valid for new databases — use `free` (or a current paid tier like
   `basic-256mb` / `basic-1gb` for production).
2. Create **New → Web Service** pointing at the repo, with:
   - Build command: `pip install --only-binary=:all: -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Environment variable `PYTHON_VERSION=3.12.8` (also confirm the service
     shows "Python 3.12.8" in the Settings → Environment section).
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
| `CORS_ORIGINS` | static | Allowed origins. Accepts comma-separated (`https://a.com,https://b.com`), a JSON list (`["https://a.com","https://b.com"]`), a single URL, or empty. **Do not wrap the value in quotes in the Render dashboard** — they are preserved as literal characters. See `CORS_SETTINGS_FIX.md`. |

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
- **Low connection limit on Free / small plans** — the app uses a small pool
  (`min_size=1`, `max_size=5`). Bump in `app/db.py` when you upgrade the
  Postgres plan.
- **App crashes on boot with `pydantic_settings.sources.SettingsError: error parsing value for field "cors_origins"`** —
  an older build tried to parse `CORS_ORIGINS` as a pydantic `list[str]`
  before any validator ran, and pydantic-settings' default JSON-first
  parser rejected the comma-separated form. This package now stores the
  raw string and parses it after load (see `app/config.py` →
  `cors_origins_raw` + the `cors_origins` computed property). If you still
  see the error, confirm you're running the latest `app/config.py` and
  that the env value is not wrapped in quotes. See `CORS_SETTINGS_FIX.md`.
- **Build fails with `maturin failed` / `error: could not write to /usr/local/cargo/registry`** —
  Render picked a Python version (e.g. 3.14) that has no `pydantic-core`
  wheel, so pip tried to compile Rust from source. Confirm
  `PYTHON_VERSION=3.12.8` is set in the web service env, `.python-version`
  and `runtime.txt` are present at the repo root, and the build command is
  `pip install --only-binary=:all: -r requirements.txt`. See
  `BUILD_FIX_PYTHON_VERSION.md`.

## 8. Post-deploy hardening (optional)

- Add a Render cron job that calls `POST /api/reservations/expire` on a
  schedule (e.g. every 5 minutes).
- Enable Render's automatic daily Postgres backups.
- Restrict `CORS_ORIGINS` to the production frontend hostnames.
- Rotate the database password via the Render dashboard if it was ever
  exposed.

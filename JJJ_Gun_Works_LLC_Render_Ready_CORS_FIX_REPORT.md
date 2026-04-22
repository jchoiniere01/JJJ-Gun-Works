# CORS_ORIGINS settings fix — report

**Package:** `/home/user/workspace/JJJ_Gun_Works_LLC_Render_Ready/`
**Zip:**     `/home/user/workspace/JJJ_Gun_Works_LLC_Render_Ready.zip` (≈83 KB, 70 files, rebuilt 2026-04-22)

## Problem

Render boot failed with:

```
pydantic_settings.sources.SettingsError: error parsing value for field
"cors_origins" from source "EnvSettingsSource"
```

Cause: pydantic-settings v2 JSON-decodes `list[str]` env values *before*
any `@field_validator(mode="before")` runs, so the comma-separated form
`https://a.com,https://b.com` (the natural Render dashboard form) never
reaches the splitter.

## Fix

In `app/config.py`:

- `cors_origins` is no longer a directly env-loaded `List[str]`. It is a
  `@computed_field` property.
- A new string field `cors_origins_raw` (aliased to env var `CORS_ORIGINS`)
  holds the raw value. Because its type is `str`, pydantic-settings does
  not attempt JSON decoding.
- The property accepts comma-separated, single URL, JSON list literal, and
  empty/unset input.
- A `mode="before"` validator on `cors_origins_raw` coerces programmatic
  `list`/`tuple` input back to a comma-joined string so
  `Settings(cors_origins_raw=[...])` also works.
- `model_config` adds `populate_by_name=True` so both
  `Settings(cors_origins_raw=...)` and env var `CORS_ORIGINS` populate the
  field.

`app/main.py` (`CORSMiddleware(allow_origins=settings.cors_origins, ...)`)
is unchanged — it still reads the parsed list.

## Changed files

| File | Change |
| --- | --- |
| `app/config.py` | Reworked CORS handling as described above |
| `.env.example` | Added a comment block listing the accepted `CORS_ORIGINS` forms |
| `.env.render.example` | Same — comment above `CORS_ORIGINS=` |
| `render.yaml` | Added a comment above the `CORS_ORIGINS` env-var block; value unchanged (comma-separated) |
| `README_RENDER_DEPLOY.md` | Env var table entry updated; new troubleshooting bullet for the pydantic-settings error |
| `CHANGELOG_RENDER_PACKAGE.md` | New bullet under "Known follow-ups" describing the fix and pointing to `CORS_SETTINGS_FIX.md` |
| `CORS_SETTINGS_FIX.md` (new) | Full error text, root cause, the new code, accepted input table, dashboard hygiene notes |

Not touched: `archive/sqlserver/**`, `reference/**`, live Python outside
`app/config.py`, `pyproject.toml`, `requirements.txt`.

## Validation

### Byte-compile

```
$ python -m compileall app
Listing 'app'...        OK
Listing 'app/api'...    OK
Listing 'app/services'... OK
```

### Import + parse test

Script imported `Settings` (with `_env_file=None` to isolate from any
stray dotenv), set `CORS_ORIGINS` to each of the accepted forms, and
asserted the resulting `settings.cors_origins` list:

```
OK  comma-separated   -> ['https://a.com', 'https://b.com', 'https://c.com']
OK  JSON list         -> ['https://a.com', 'https://b.com']
OK  single URL        -> ['https://only.example.com']
OK  empty string      -> []
OK  whitespace        -> []
OK  trailing comma    -> ['https://a.com', 'https://b.com']
OK  unset (default)   -> ['http://localhost:5173', 'http://localhost:3000']
OK  programmatic list -> ['https://x.com', 'https://y.com']
```

All 8 cases pass; no `SettingsError` raised.

### One-liner you can re-run

```bash
CORS_ORIGINS='https://a.com,https://b.com' \
python -c "from app.config import Settings; print(Settings(_env_file=None).cors_origins)"
# -> ['https://a.com', 'https://b.com']

CORS_ORIGINS='["https://a.com","https://b.com"]' \
python -c "from app.config import Settings; print(Settings(_env_file=None).cors_origins)"
# -> ['https://a.com', 'https://b.com']

CORS_ORIGINS='' \
python -c "from app.config import Settings; print(Settings(_env_file=None).cors_origins)"
# -> []
```

### Zip rebuild

```
/home/user/workspace/JJJ_Gun_Works_LLC_Render_Ready.zip   85,444 bytes   70 files
```

Rebuilt with `zip -r ... -x "*/__pycache__/*" "*.pyc"`. File count grew by
1 vs. the previous zip (`CORS_SETTINGS_FIX.md`).

## Remaining manual Render dashboard steps

1. Open the web service → Settings → Environment.
2. Confirm `CORS_ORIGINS` does **not** have surrounding quote characters.
   The dashboard preserves them literally, which would produce entries
   like `'"https://a.com'`.
3. Trigger a redeploy after pushing the new code — Render needs to pick
   up the new `app/config.py`.
4. Confirm `/api/health` responds; the CORS settings error would be
   raised before FastAPI started, so a 200 from `/api/health` is proof
   the fix is live.

## Secrets

No secrets added or exposed. All edits are to code, docs, and comments;
no credentials or hostnames were embedded.

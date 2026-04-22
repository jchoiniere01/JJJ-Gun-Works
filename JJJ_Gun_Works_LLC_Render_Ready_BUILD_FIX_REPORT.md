# Render Build Fix Report — Python 3.12.8 pin

**Package:** `/home/user/workspace/JJJ_Gun_Works_LLC_Render_Ready/`
**Zip:**     `/home/user/workspace/JJJ_Gun_Works_LLC_Render_Ready.zip` (≈80 KB, 69 files, rebuilt 2026-04-22)

## Problem

Render was building the service against Python 3.14, which has no prebuilt
`pydantic-core` manylinux wheel. pip fell back to compiling the Rust core
via `maturin`/`cargo`, which failed against Render's read-only cargo
registry (`error: could not write to /usr/local/cargo/registry`).

## Fix applied (package-only; archives untouched)

| File | Change |
| --- | --- |
| `.python-version` (new) | `3.12.8` |
| `runtime.txt` (new) | `python-3.12.8` |
| `render.yaml` | Added `PYTHON_VERSION=3.12.8` env var on the web service; build command switched to `pip install --only-binary=:all: -r requirements.txt` |
| `pyproject.toml` | `requires-python = ">=3.11"` → `">=3.11,<3.13"` |
| `requirements.txt` | Added explicit `pydantic-core==2.27.2` pin (cp312 manylinux wheel available); added a header comment explaining the wheel constraint |
| `README_RENDER_DEPLOY.md` | Added a "Python version" subsection under Prerequisites; updated the manual-create build command; added a troubleshooting bullet for the maturin/cargo error |
| `CHANGELOG_RENDER_PACKAGE.md` | New bullet documenting the 3.12.8 pin and pointer to `BUILD_FIX_PYTHON_VERSION.md` |
| `BUILD_FIX_PYTHON_VERSION.md` (new) | Full error log, root-cause explanation, list of changes, local verification commands, manual Render dashboard steps, and future-maintenance guidance |

Web service `plan: starter` and database `plan: free` were not touched by
this change. Archive (`archive/sqlserver/**`) and reference
(`reference/**`) are unchanged.

## Validation

### Local Python

```
$ python --version
Python 3.12.8
```

### Byte-compile

```
$ python -m compileall app
Listing 'app'...              OK
Listing 'app/api'...          OK
Listing 'app/services'...     OK
```

All modules byte-compile cleanly on 3.12.8.

### Grep for `3.14` references

Only expected hits remain, all inside documentation that intentionally
explains the failed interpreter:

```
BUILD_FIX_PYTHON_VERSION.md:28,30,75,89  (error log + guidance)
CHANGELOG_RENDER_PACKAGE.md:129          (changelog bullet)
README_RENDER_DEPLOY.md:23,153           (Python version note + troubleshooting)
```

No `3.14` references in `render.yaml`, `.python-version`, `runtime.txt`,
`requirements.txt`, `pyproject.toml`, or any live Python source. ✅

### Grep for `PYTHON_VERSION` / pin sanity

```
render.yaml:          PYTHON_VERSION value: 3.12.8
.python-version:      3.12.8
runtime.txt:          python-3.12.8
pyproject.toml:       requires-python = ">=3.11,<3.13"
```

All three pin mechanisms agree. ✅

### Zip rebuild

```
/home/user/workspace/JJJ_Gun_Works_LLC_Render_Ready.zip   81,772 bytes   69 files
```

Rebuilt with `zip -r ... -x "*/__pycache__/*" "*.pyc"`. File count grew by
3 vs. the previous zip: `.python-version`, `runtime.txt`,
`BUILD_FIX_PYTHON_VERSION.md`.

## Remaining manual Render dashboard steps

These cannot be expressed in the repo and must be done in the Render UI
after the new code is pushed:

1. **Confirm the env var propagated.** Web service → Settings → Environment
   should list `PYTHON_VERSION=3.12.8`. If you updated an existing service
   whose Blueprint sync is off, add it manually.
2. **Clear the build cache** before the next deploy. Render caches the Python
   toolchain layer by version; without a cache clear it may reuse the 3.14
   layer. In the dashboard: Manual Deploy → "Clear build cache & deploy".
3. **Verify the interpreter in the build log.** The first build-phase line
   should read `==> Using Python version 3.12.8` (or similar). If it still
   says 3.14, the pin files were not picked up — double-check they are at
   the repo root, not inside a subdirectory.
4. **If using a paid plan later**, the same Python pin applies; only the
   database `plan:` / web service `plan:` strings change.

## Secrets

No secrets added or exposed. All edits are to plan/version strings,
dependency pins, documentation, and comments.

# Build fix — Python runtime pin (3.12.8)

## Observed error

Render build logs showed:

```
Collecting pydantic-core==2.27.2
  Downloading pydantic_core-2.27.2.tar.gz (...)
  Installing build dependencies ...
  ...
  Running `maturin build --release ...`
  error: could not write to `/usr/local/cargo/registry/cache/...`
  Caused by: Read-only file system (os error 30)
  ...
  ERROR: Failed building wheel for pydantic-core
```

Variants of the same failure surface as:

- `error: no Rust compiler found` / `cargo: command not found`
- `maturin failed`
- `note: This error originates from a subprocess, and is likely not a
  problem with pip.`

## Root cause

Render's Python build image was defaulting to **Python 3.14**. `pydantic-core`
(the Rust-backed core of pydantic v2) does not publish manylinux wheels for
3.14 yet, so pip fell back to the sdist and tried to compile Rust locally
via `maturin`. Render's build sandbox has a **read-only cargo registry**,
and the build step runs without a writable `CARGO_HOME` / `RUSTUP_HOME`, so
the compile fails before any crate can be downloaded.

The same trap affects `orjson`, `msgspec`, `tiktoken`, `cryptography`, and
any other PEP 517 project that vendors Rust or C and has no wheel for the
interpreter pip selected.

## What changed

All changes are in the Render-ready package only; archive and reference
docs are untouched.

| File | Change |
| --- | --- |
| `.python-version` (new) | `3.12.8` — primary signal pip/pyenv/Render read |
| `runtime.txt` (new) | `python-3.12.8` — belt-and-braces for older Render runtime detection |
| `render.yaml` | Added `PYTHON_VERSION=3.12.8` to the web service `envVars`; changed build command to `pip install --only-binary=:all: -r requirements.txt` so any wheel-less package fails fast instead of invoking cargo |
| `pyproject.toml` | `requires-python = ">=3.11"` → `">=3.11,<3.13"` to match the pin |
| `requirements.txt` | Added `pydantic-core==2.27.2` explicitly (has a cp312 manylinux_2_17_x86_64 wheel on PyPI); added a header comment explaining the wheel constraint |

Existing dependency versions (`fastapi==0.115.6`, `pydantic==2.10.5`,
`psycopg[binary]==3.2.3`, `uvicorn[standard]==0.34.0`, etc.) were already
known to publish cp312 manylinux wheels; only `pydantic-core` needed an
explicit pin because it is the dependency that was attempting the source
build.

## Why `--only-binary=:all:`

With `--only-binary=:all:`, pip refuses to fall back to an sdist under any
circumstance. If a future dependency bump picks a version whose wheel matrix
doesn't cover `cp312-manylinux_2_17_x86_64`, the build fails with a clean
`ERROR: Could not find a version that satisfies the requirement ...` message
instead of silently trying (and failing) to compile from source. This is
much easier to diagnose than a 300-line Rust traceback.

## Verification you can run locally

```bash
# Confirm the pinned interpreter would be selected (requires pyenv or asdf):
cat .python-version
cat runtime.txt
grep PYTHON_VERSION render.yaml

# Confirm no 3.14 references remain in the package:
grep -rn "3\.14" .

# Confirm the requirements resolve to wheels (dry-run, no install):
python3.12 -m pip install --dry-run --only-binary=:all: -r requirements.txt
```

## Manual Render dashboard steps (post-push)

If the Blueprint doesn't pick up the env var change automatically:

1. Open the web service → Settings → Environment.
2. Confirm `PYTHON_VERSION=3.12.8` is present. If not, add it.
3. Trigger a manual **Clear build cache & deploy** so Render doesn't reuse
   the previous 3.14 environment layers.
4. In the Events tab, confirm the first build log line reads
   `==> Using Python version 3.12.8`.

## Future maintenance

- Before bumping any pydantic / pydantic-core / psycopg / orjson version,
  check the project page on PyPI → "Download files" and confirm a
  `cp312-manylinux_2_17_x86_64` wheel exists.
- When Render announces support for a newer Python (say 3.13), update
  `.python-version`, `runtime.txt`, and `PYTHON_VERSION` together, and bump
  `requires-python` to match.
- Do not remove `--only-binary=:all:` without a strong reason — it's the
  single biggest safety net against this class of failure.

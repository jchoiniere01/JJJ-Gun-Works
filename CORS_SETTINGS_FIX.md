# CORS_ORIGINS settings fix

## Observed error

On boot the web service crashed with:

```
pydantic_settings.sources.SettingsError: error parsing value for field
"cors_origins" from source "EnvSettingsSource"
```

This happened whenever `CORS_ORIGINS` was set to a plain comma-separated
string (e.g. `https://a.com,https://b.com`) — which is the natural form to
enter in the Render dashboard and the form the `.env.example` file
suggested.

## Root cause

pydantic-settings v2 gives complex env values (anything typed `list`, `dict`,
`set`, `tuple`, or a model) to a **JSON-first** decoder *before* any
`@field_validator(mode="before")` runs. A comma-separated string isn't
valid JSON, so the decoder raises `SettingsError`. The validator never gets
a chance to split on commas.

The old field looked like:

```python
cors_origins: List[str] = Field(default_factory=lambda: [...])

@field_validator("cors_origins", mode="before")
def split_cors_origins(cls, value: str | list[str]) -> list[str]:
    ...
```

That pattern is widely shown in tutorials and is genuinely broken on
pydantic-settings v2 for env sources.

## Fix

The env-backed field is now a plain `str`, so pydantic-settings' env
parser does no JSON decoding. The parsed list is exposed as a
`@computed_field` property:

```python
cors_origins_raw: str = Field(
    default="http://localhost:5173,http://localhost:3000",
    validation_alias="CORS_ORIGINS",
)

@computed_field
@property
def cors_origins(self) -> list[str]:
    raw = (self.cors_origins_raw or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    return [p.strip() for p in raw.split(",") if p.strip()]
```

A small `mode="before"` validator on `cors_origins_raw` also coerces
programmatic `list[str]` inputs into the same comma-separated string form,
so `Settings(cors_origins_raw=[...])` still works in tests.

### Accepted input forms

| Env value                             | Result                                |
| ------------------------------------- | ------------------------------------- |
| unset                                 | `["http://localhost:5173","http://localhost:3000"]` (default) |
| `""`                                  | `[]`                                  |
| `"   "`                               | `[]`                                  |
| `"https://only.example.com"`          | `["https://only.example.com"]`        |
| `"https://a.com,https://b.com"`       | `["https://a.com","https://b.com"]`   |
| `"https://a.com, https://b.com"`      | `["https://a.com","https://b.com"]` (whitespace trimmed) |
| `"https://a.com,,https://b.com,"`     | `["https://a.com","https://b.com"]` (empty entries dropped) |
| `'["https://a.com","https://b.com"]'` | `["https://a.com","https://b.com"]`   |

### Consumer

`app/main.py` already does:

```python
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, ...)
```

No call-site changes needed.

## Verification

A repeatable test that imports `Settings`, sets `CORS_ORIGINS` to each
form, and asserts the parsed list matches expectation ships in the
`CORS_FIX_REPORT.md` sibling file and in this package's
`JJJ_Gun_Works_LLC_Render_Ready_CORS_FIX_REPORT.md` (the one-liner / script
used to validate the fix).

## Render dashboard hygiene

- Do **not** wrap the value in quotes. The dashboard preserves quotes as
  literal characters, so `"https://a.com,https://b.com"` (with quotes)
  would parse as `['"https://a.com', 'https://b.com"']`.
- Prefer the comma-separated form; the JSON list form also works but is
  more error-prone to type correctly.
- An empty value disables CORS (equivalent to `allow_origins=[]`).

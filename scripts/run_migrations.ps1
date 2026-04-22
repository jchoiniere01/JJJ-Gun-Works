# =============================================================================
# JJJ Gun Works LLC — PostgreSQL migration runner (PowerShell).
#
# Applies the three PG migration scripts, in order, to a target database.
# Works for:
#   * A local Postgres (started via docker-compose.postgres.yml)
#   * The Render managed Postgres External URL
#
# Requirements:
#   * `psql` on PATH. On Windows, install the PostgreSQL client from
#     https://www.postgresql.org/download/windows/ and add the `bin\` dir to PATH.
#
# Usage examples:
#   # Using DATABASE_URL from the current shell / .env
#   .\scripts\run_migrations.ps1
#
#   # Explicit URL (use the Render External Database URL)
#   .\scripts\run_migrations.ps1 -DatabaseUrl "postgresql://user:pass@host:5432/db?sslmode=require"
#
#   # Only run schema DDL, skip seed
#   .\scripts\run_migrations.ps1 -SkipSeed
# =============================================================================

[CmdletBinding()]
param(
    [string] $DatabaseUrl,
    [string] $EnvFile = ".env",
    [switch] $SkipSeed,
    [switch] $SkipFunctions
)

$ErrorActionPreference = "Stop"
$script:ScriptRoot = Split-Path -Parent $PSCommandPath
$script:PackageRoot = Split-Path -Parent $script:ScriptRoot
$script:SqlDir = Join-Path $script:PackageRoot "sql"

function Resolve-DatabaseUrl {
    param([string] $ExplicitUrl, [string] $EnvPath)

    if ($ExplicitUrl) { return $ExplicitUrl }
    if ($env:DATABASE_URL) { return $env:DATABASE_URL }

    if (Test-Path $EnvPath) {
        Write-Host "Reading DATABASE_URL from $EnvPath"
        foreach ($line in Get-Content $EnvPath) {
            if ($line -match '^\s*DATABASE_URL\s*=\s*(.+?)\s*$') {
                return $matches[1].Trim('"').Trim("'")
            }
        }
    }

    throw "DATABASE_URL not provided. Pass -DatabaseUrl, set `$env:DATABASE_URL, or put it in $EnvPath."
}

function Assert-Psql {
    $psql = Get-Command psql -ErrorAction SilentlyContinue
    if (-not $psql) {
        throw "psql not found on PATH. Install PostgreSQL client tools and retry."
    }
    Write-Host ("psql found at {0}" -f $psql.Source)
}

function Invoke-SqlFile {
    param([string] $Url, [string] $Path, [string] $Label)

    if (-not (Test-Path $Path)) {
        throw "Missing migration file: $Path"
    }
    Write-Host "`n=== Running $Label: $(Split-Path -Leaf $Path) ==="
    & psql $Url -v ON_ERROR_STOP=1 -f $Path
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed (psql exit $LASTEXITCODE)"
    }
    Write-Host "=== $Label OK ==="
}

Assert-Psql
$databaseUrl = Resolve-DatabaseUrl -ExplicitUrl $DatabaseUrl -EnvPath (Join-Path $script:PackageRoot $EnvFile)

# Mask credentials before echoing.
$maskedUrl = ($databaseUrl -replace '(postgres(?:ql)?:\/\/)([^:@]+):([^@]+)@', '$1$2:****@')
Write-Host "Target DATABASE_URL: $maskedUrl"

Invoke-SqlFile -Url $databaseUrl `
    -Path (Join-Path $script:SqlDir "001_inventory_reservations.postgres.sql") `
    -Label "001 inventory + reservations schema"

if (-not $SkipFunctions) {
    Invoke-SqlFile -Url $databaseUrl `
        -Path (Join-Path $script:SqlDir "002_reservation_functions.postgres.sql") `
        -Label "002 reservation plpgsql functions"
} else {
    Write-Host "Skipping 002 reservation functions (--SkipFunctions)"
}

if (-not $SkipSeed) {
    Invoke-SqlFile -Url $databaseUrl `
        -Path (Join-Path $script:SqlDir "003_seed_configurator_options.postgres.sql") `
        -Label "003 configurator seed"
} else {
    Write-Host "Skipping 003 seed (--SkipSeed)"
}

Write-Host "`nAll migrations completed successfully."

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))

$exe = Join-Path (Get-Location) "dist/Telemetry Frame Mapper/Telemetry Frame Mapper.exe"
if (-not (Test-Path $exe)) {
    throw "Windows bundle is missing: $exe"
}

$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("tfm-windows-smoke-" + [guid]::NewGuid())
$env:LOCALAPPDATA = $smokeRoot
New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null

# The frozen exe can bundle rasterio's/laspy's Python files fine while still
# missing GDAL/PROJ data or a native DLL that only a real import would surface.
# Fail fast, before the slower health check below, if the packaged app cannot
# import them. Runs after LOCALAPPDATA is redirected, same as the real launch
# below, so it never touches the runner's actual user profile.
$importCheck = & $exe --check-reconstruction-deps 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Packaged app cannot import laspy/rasterio: $importCheck"
}
Write-Host $importCheck
$stdout = Join-Path $smokeRoot "stdout.log"
$stderr = Join-Path $smokeRoot "stderr.log"
$process = Start-Process -FilePath $exe -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr

try {
    $deadline = (Get-Date).AddSeconds(90)
    do {
        if ($process.HasExited) {
            throw "Packaged app exited before health check. stderr: $(Get-Content $stderr -Raw)"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
        } catch {
            Start-Sleep -Seconds 2
        }
    } until ($health.status -eq "ok" -or (Get-Date) -ge $deadline)

    if ($health.status -ne "ok") {
        throw "Packaged app did not become healthy. stderr: $(Get-Content $stderr -Raw)"
    }

    $database = Join-Path $smokeRoot "Telemetry Frame Mapper/data/drone_mapping.db"
    if (-not (Test-Path $database)) {
        throw "Packaged app did not create its SQLite database under LOCALAPPDATA"
    }

    $actualHead = python -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select version_num from alembic_version').fetchone()[0])" $database
    $expectedHead = python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_current_head())"
    if ($LASTEXITCODE -ne 0 -or $actualHead.Trim() -ne $expectedHead.Trim()) {
        throw "Migration head mismatch: database=$actualHead source=$expectedHead"
    }

    Write-Host "Windows bundle health and migration smoke passed at revision $actualHead"
} finally {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit()
    }
}

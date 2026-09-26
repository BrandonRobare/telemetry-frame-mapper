$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))

$exe = Join-Path (Get-Location) "dist/Telemetry Frame Mapper/Telemetry Frame Mapper.exe"
if (-not (Test-Path $exe)) {
    throw "Windows bundle is missing: $exe"
}

$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("tfm-windows-smoke-" + [guid]::NewGuid())
$env:LOCALAPPDATA = $smokeRoot
New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null

# A bare import survives a bundle with no GDAL/PROJ data -- rasterio only
# reads it lazily on first CRS or driver use -- so this probe actually
# resolves a CRS through PROJ, round-trips a GeoTIFF through GDAL, and writes
# a LAZ point cloud through the lazrs backend. Fail fast, before the slower
# health check below. Runs after LOCALAPPDATA is redirected, same as the real
# launch below, so it never touches the runner's actual user profile.
#
# Redirect to files rather than `2>&1`: a harmless native warning on stderr
# (e.g. GDAL griping before its data path is set) becomes a PowerShell
# terminating error under $ErrorActionPreference = "Stop" when merged into
# the success stream, which would fail this check for the wrong reason. The
# exit code is the actual signal.
$capabilityStdout = Join-Path $smokeRoot "capability-check-stdout.log"
$capabilityStderr = Join-Path $smokeRoot "capability-check-stderr.log"
$capabilityProcess = Start-Process -FilePath $exe -ArgumentList "--check-reconstruction-deps" `
    -PassThru -Wait -RedirectStandardOutput $capabilityStdout -RedirectStandardError $capabilityStderr
$capabilityOutput = "$(Get-Content $capabilityStdout -Raw)$(Get-Content $capabilityStderr -Raw)"
if ($capabilityProcess.ExitCode -ne 0) {
    throw "Packaged app cannot use laspy/rasterio: $capabilityOutput"
}
Write-Host $capabilityOutput
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

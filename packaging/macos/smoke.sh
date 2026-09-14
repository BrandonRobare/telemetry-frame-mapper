#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

app="$repo_root/dist/Telemetry Frame Mapper.app/Contents/MacOS/Telemetry Frame Mapper"
if [[ ! -x "$app" ]]; then
    printf 'macOS application bundle is missing or not executable: %s\n' "$app" >&2
    exit 1
fi

smoke_root="$(mktemp -d "${TMPDIR:-/tmp}/tfm-macos-smoke.XXXXXX")"
stdout="$smoke_root/stdout.log"
stderr="$smoke_root/stderr.log"
app_pid=""
app_data="$smoke_root/Library/Application Support/Telemetry Frame Mapper"

# #859: the app must never inherit runtime selectors from the CI environment.
# Scrub everything and re-approve an explicit allowlist at launch (below);
# prove it with a sentinel DATABASE_URL that must stay untouched.
sentinel_db="$smoke_root/never-touch.db"
export DATABASE_URL="sqlite:///$sentinel_db"   # must NOT reach the app
export DRONE_MAPPING_PIN_HASH="sentinel-pin"   # must NOT reach the app

# Sanitized configuration: storage roots, logs and backup locations all live
# under the temporary home, and background watchers/backup are disabled, so
# the smoke cannot read or write real user data even if it boots (#859).
mkdir -p "$app_data"
cat > "$app_data/config.yaml" <<YAML
imports_dir: "$smoke_root/imports"
processed_dir: "$smoke_root/processed"
exports_dir: "$smoke_root/exports"
data_dir: "$smoke_root/data"
logging:
  enabled: false
deployment:
  host: "127.0.0.1"
  port: 8000
  cors_origins:
    - "http://localhost:5173"
  allow_unauthenticated_lan: false
pin_lock:
  enabled: false
api_key:
  enabled: false
auto_import:
  enabled: false
  roots: []
backup:
  local_destinations: []
  rclone_remote: ""
  pre_migration_keep: 0
  targets: {}
  schedule:
    enabled: false
    target: ""
    daily_at: "02:00"
remote_worker:
  enabled: false
webodm:
  enabled: false
cesium_ion:
  enabled: false
YAML

cleanup() {
    if [[ -n "$app_pid" ]] && kill -0 "$app_pid" 2>/dev/null; then
        kill "$app_pid" 2>/dev/null || true
        wait "$app_pid" 2>/dev/null || true
    fi
    # The sentinel database proves the inherited DATABASE_URL never leaked.
    if [[ -e "$sentinel_db" ]]; then
        printf '%s\n' "FAIL: smoke runtime mutated the inherited DATABASE_URL sentinel" >&2
        rm -rf "$smoke_root"
        exit 1
    fi
    rm -rf "$smoke_root"
}
trap cleanup EXIT

# Launch with an explicit environment allowlist: the bare PATH is deliberate
# so the runtime-hook Homebrew discovery under #832 is exercised.
env -i \
    HOME="$smoke_root" \
    PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
    TMPDIR="${TMPDIR:-/tmp}" \
    "$app" >"$stdout" 2>"$stderr" &
app_pid=$!
deadline=$((SECONDS + 90))
health_url="http://127.0.0.1:8000/health"

while (( SECONDS < deadline )); do
    if ! kill -0 "$app_pid" 2>/dev/null; then
        printf '%s\n' "Packaged app exited before health check. stderr:" >&2
        cat "$stderr" >&2
        exit 1
    fi
    if curl --fail --silent --show-error --max-time 2 "$health_url" >/dev/null; then
        break
    fi
    sleep 2
done

if ! curl --fail --silent --show-error --max-time 2 "$health_url" >/dev/null; then
    printf '%s\n' "Packaged app did not become healthy. stderr:" >&2
    cat "$stderr" >&2
    exit 1
fi

for path in "$app_data/config.yaml" "$app_data/data" "$app_data/imports" "$app_data/processed" "$app_data/exports"; do
    if [[ ! -e "$path" ]]; then
        printf 'Packaged app did not create expected data path: %s\n' "$path" >&2
        exit 1
    fi
done

database="$app_data/data/drone_mapping.db"
if [[ ! -f "$database" ]]; then
    printf '%s\n' "Packaged app did not create its SQLite database under Application Support" >&2
    exit 1
fi

actual_head="$(uv run --frozen --no-sync python -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select version_num from alembic_version').fetchone()[0])" "$database")"
expected_head="$(uv run --frozen --no-sync python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_current_head())")"
if [[ "$actual_head" != "$expected_head" ]]; then
    printf 'Migration head mismatch: database=%s source=%s\n' "$actual_head" "$expected_head" >&2
    exit 1
fi

printf 'macOS bundle health and migration smoke passed at revision %s\n' "$actual_head"

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

cleanup() {
    if [[ -n "$app_pid" ]] && kill -0 "$app_pid" 2>/dev/null; then
        kill "$app_pid" 2>/dev/null || true
        wait "$app_pid" 2>/dev/null || true
    fi
    rm -rf "$smoke_root"
}
trap cleanup EXIT

HOME="$smoke_root" "$app" >"$stdout" 2>"$stderr" &
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

app_data="$smoke_root/Library/Application Support/Telemetry Frame Mapper"
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

actual_head="$(python -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select version_num from alembic_version').fetchone()[0])" "$database")"
expected_head="$(python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_current_head())")"
if [[ "$actual_head" != "$expected_head" ]]; then
    printf 'Migration head mismatch: database=%s source=%s\n' "$actual_head" "$expected_head" >&2
    exit 1
fi

printf 'macOS bundle health and migration smoke passed at revision %s\n' "$actual_head"

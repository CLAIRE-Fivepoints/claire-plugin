#!/usr/bin/env bash
# fivepoints test-env-start
# Starts the full TFI One stack for local testing (SQL Server + API + frontend).
# Run from the TFI One project root directory.
#
# Usage:
#   claire fivepoints test-env-start [--path /path/to/TFIOneGit]

set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: claire fivepoints test-env-start [--path /path/to/TFIOneGit]"
    echo ""
    echo "Start the full TFI One stack for local testing."
    echo "  SQL Server (Docker) + .NET API + Vite frontend"
    echo ""
    echo "Options:"
    echo "  --path <dir>    Path to TFI One project root (default: current directory)"
    echo "  --agent-help    Show LLM-optimized help"
    echo "  --help, -h      Show this help"
    exit 0
fi

if [[ "${1:-}" == "--agent-help" ]]; then
    cat <<'HELP'
# fivepoints test-env-start — LLM Agent Guide

## Purpose
Start the full TFI One stack for local testing: SQL Server (Docker) + .NET API + Vite frontend.
Run this at the start of every tester or dev self-test session (step 1 of the checklist).

## Usage
```bash
claire fivepoints test-env-start
claire fivepoints test-env-start --path /Users/andreperez/TFIOneGit
```

## What it does
1. Starts Docker SQL Server container (tfione-sqlserver)
2. Starts the .NET API on https://localhost:58337
3. Starts the Vite frontend on https://localhost:5173
4. Waits for both services to respond
5. Prints PIDs for clean shutdown

## Output
```
✅ Environment ready
   API:      https://localhost:58337
   Swagger:  https://localhost:58337/swagger
   UI:       https://localhost:5173
   API_PID=12345
   VITE_PID=12346
   Shutdown: kill 12345 12346 && docker stop tfione-sqlserver
```

## Shutdown
```bash
kill $API_PID $VITE_PID
docker stop tfione-sqlserver
```

## Notes
- Must be run from the TFI One project root (or pass --path)
- SQL Server container must exist (docker run on first use creates it automatically)
- Sets ASPNETCORE_ENVIRONMENT=Development automatically (prevents silent login failure in Production mode)
- On macOS: auto-detects SA password from existing container and injects SQL auth connection string (avoids Kerberos failure)
HELP
    exit 0
fi

PROJECT_DIR="${PWD}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --path)
            PROJECT_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: claire fivepoints test-env-start [--path /path/to/TFIOneGit]" >&2
            echo "Run with --help for full usage." >&2
            exit 1
            ;;
    esac
done

if [[ ! -f "$PROJECT_DIR/com.tfione.sln" ]]; then
    echo "❌ Not a TFI One project directory: $PROJECT_DIR" >&2
    echo "   Expected com.tfione.sln to exist." >&2
    echo "   Run from the project root or pass --path /path/to/TFIOneGit" >&2
    exit 1
fi

cd "$PROJECT_DIR"

echo "[1/4] Starting SQL Server..."
# L3: Auto-detect SA password from existing container env before falling back to default
SA_PASSWORD="YourStrong!Passw0rd"
if docker ps -a --format '{{.Names}}' | grep -q '^tfione-sqlserver$'; then
    _detected_pw=$(docker inspect tfione-sqlserver --format='{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
        | grep '^MSSQL_SA_PASSWORD=' | head -1 | cut -d= -f2- || true)
    if [[ -n "$_detected_pw" ]]; then
        SA_PASSWORD="$_detected_pw"
        echo "  SA password auto-detected from existing container"
    fi
    docker start tfione-sqlserver 2>/dev/null || true
else
    echo "  Container not found — creating tfione-sqlserver..."
    docker run -d \
        --name tfione-sqlserver \
        -e 'ACCEPT_EULA=Y' \
        -e "MSSQL_SA_PASSWORD=${SA_PASSWORD}" \
        -p 1433:1433 \
        mcr.microsoft.com/mssql/server:2022-latest
fi
sleep 5

echo "[2/4] Starting .NET API..."
# L1: Set ASPNETCORE_ENVIRONMENT=Development so RecaptchaSettings.RecaptchaOn defaults to false.
# Without this, the API runs in Production mode and silently rejects programmatic logins (HTTP 200,
# userName:null, token:null with no error message).
export ASPNETCORE_ENVIRONMENT=Development

# L2: On macOS with Docker SQL Server, override connection string to use SQL auth (avoid Kerberos).
# The default appsettings.json uses Integrated Security=True which fails on macOS with:
# "GSSAPI operation failed: The context has expired and can no longer be used"
if [[ "$(uname -s)" == "Darwin" ]]; then
    export ConnectionStrings__tfione="Server=localhost,1433;Database=tfi_one;User Id=sa;Password=${SA_PASSWORD};TrustServerCertificate=True;Encrypt=False"
    echo "  macOS detected — injecting SQL auth connection string (avoids Kerberos)"
fi

dotnet run \
    --project com.tfione.api/com.tfione.api.csproj \
    --urls "https://localhost:58337" \
    --no-launch-profile \
    > /tmp/tfione-api.log 2>&1 &
API_PID=$!

echo "[3/4] Starting frontend..."
(cd com.tfione.web && npm run dev > /tmp/tfione-vite.log 2>&1) &
VITE_PID=$!

echo "[4/4] Waiting for services (heartbeat every 15s)..."
# Heartbeat loop: poll all three services at 2s intervals, print a status line
# every 15s. Silence for >30s previously looked identical to "script crashed" —
# the heartbeat makes booting vs. hung vs. failed unambiguous.
API_READY=false
VITE_READY=false
SQL_READY=false
WAIT_DEADLINE=60   # seconds — same as previous max for the API
START_TS=$(date +%s)
LAST_HEARTBEAT=$START_TS

probe_sql() {
    docker ps --filter 'name=^tfione-sqlserver$' --filter 'status=running' --format '{{.Names}}' \
        | grep -q '^tfione-sqlserver$'
}
probe_api() {
    curl -sk "https://localhost:58337/swagger/index.html" > /dev/null 2>&1
}
probe_vite() {
    curl -sk "https://localhost:5173" > /dev/null 2>&1 \
        || curl -sk "http://localhost:5173" > /dev/null 2>&1
}

status_word() { [[ "$1" == "true" ]] && echo up || echo down; }

while :; do
    NOW=$(date +%s)
    ELAPSED=$((NOW - START_TS))

    if probe_sql; then SQL_READY=true; else SQL_READY=false; fi
    if [[ "$API_READY" != "true" ]] && probe_api; then API_READY=true; fi
    if [[ "$VITE_READY" != "true" ]] && probe_vite; then VITE_READY=true; fi

    if [[ "$API_READY" == "true" && "$VITE_READY" == "true" ]]; then
        break
    fi
    if [[ $ELAPSED -ge $WAIT_DEADLINE ]]; then
        break
    fi

    if (( NOW - LAST_HEARTBEAT >= 15 )); then
        printf '  [%ds] booting: sqlserver=%s api=%s vite=%s\n' \
            "$ELAPSED" \
            "$(status_word "$SQL_READY")" \
            "$(status_word "$API_READY")" \
            "$(status_word "$VITE_READY")"
        LAST_HEARTBEAT=$NOW
    fi
    sleep 2
done

[[ "$SQL_READY"  != "true" ]] && echo "⚠️  SQL Server not ready after ${WAIT_DEADLINE}s — docker container did not reach 'running' state"
[[ "$API_READY"  != "true" ]] && echo "⚠️  API not ready after ${WAIT_DEADLINE}s — check /tmp/tfione-api.log"
[[ "$VITE_READY" != "true" ]] && echo "⚠️  Vite not ready after ${WAIT_DEADLINE}s — check /tmp/tfione-vite.log"

echo ""
echo "✅ Environment ready"
echo "   API:      https://localhost:58337"
echo "   Swagger:  https://localhost:58337/swagger"
echo "   UI:       https://localhost:5173"
echo "   API_PID=$API_PID"
echo "   VITE_PID=$VITE_PID"
echo "   Shutdown: kill $API_PID $VITE_PID && docker stop tfione-sqlserver"

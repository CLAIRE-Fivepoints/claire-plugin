#!/usr/bin/env bash
# fivepoints smoke-test
# Verifies the local TFI One stack is healthy before manual testing.
#
# Issue #118 (CLAIRE-Fivepoints/claire-plugin) — burned 1h on issue #14
# debugging environment problems (wrong SA password, port conflicts,
# empty dropdowns) because no automated way existed to confirm the stack
# was up. This script is the gate.
#
# Exit codes:
#   0 — all checks passed
#   1 — at least one check failed (failed checks listed)

set -uo pipefail

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage: claire fivepoints smoke-test [OPTIONS]

Verify the local TFI One stack is healthy.

Checks (in order):
  1. Docker container 'tfione-sqlserver' is running
  2. API swagger.json reachable at https://localhost:58337
  3. Login as prime.user returns a non-empty bearer token
  4. GET /references/StateType returns a non-empty list (Bearer auth)
  5. GET /references/CountyType returns a non-empty list (Bearer auth)
  6. GET /users/organization returns 200 (Bearer auth)

Options:
  --api <url>          API base URL (default: https://localhost:58337)
  --user <name>        Login username (default: prime.user)
  --password <pwd>     Login password (default: Test1234!)
  --container <name>   Docker container name (default: tfione-sqlserver)
  --agent-help         Show LLM-optimized help
  -h, --help           Show this help

Exit codes:
  0  — all checks passed
  1  — at least one check failed
EOF
    exit 0
fi

if [[ "${1:-}" == "--agent-help" ]]; then
    cat <<'HELP'
# fivepoints smoke-test — LLM Agent Guide

## Purpose
Six-check health probe of the local TFI One stack. Runs in <5 seconds.
Use BEFORE starting manual testing — saves the recurring 30–60 min of
debugging environment issues that prompted issue #118.

## Usage
```bash
claire fivepoints smoke-test
claire fivepoints smoke-test --user other.user --password OtherPwd!
claire fivepoints smoke-test --api https://localhost:58337
```

## What it checks (in order, fail-fast)
1. `tfione-sqlserver` container running (docker ps)
2. `https://localhost:58337/swagger/v1/swagger.json` returns 200
3. POST `/auth/login` as prime.user returns a non-empty token
4. GET `/references/StateType` returns 200 + non-empty list (auth check)
5. GET `/references/CountyType` returns 200 + non-empty list
6. GET `/users/organization` returns 200

## Output (success)
```
[1/6] tfione-sqlserver running             ... OK
[2/6] swagger reachable                    ... OK
[3/6] login prime.user → token (4096 chars)... OK
[4/6] references/StateType  → list[52]     ... OK
[5/6] references/CountyType → list[3148]   ... OK
[6/6] users/organization    → 200          ... OK
✅ All 6 checks passed.
```

## Output (failure)
Each failing check is listed with hint. Exit code 1.

## Common failures
- Container not running → `docker start tfione-sqlserver` (or `claire fivepoints test-env-start`)
- Swagger 000/timeout → API not started → `claire fivepoints test-env-start`
- Login 401 → wrong password OR API in Production mode (RecaptchaOn=true silently rejects)
- Reference 401 → token missing or expired (re-run login)
- Reference list[0] → DB empty / migrations not applied → `flyway migrate`

## Pair with seed-test-data
After smoke-test passes, run `claire fivepoints seed-test-data` to populate
multi-user test data (3 roles × 2 orgs + clients + per-module data).
HELP
    exit 0
fi

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

API_BASE="https://localhost:58337"
USERNAME="prime.user"
PASSWORD="Test1234!"
CONTAINER="tfione-sqlserver"

while [[ $# -gt 0 ]]; do
    case $1 in
        --api)        API_BASE="$2"; shift 2 ;;
        --user)       USERNAME="$2"; shift 2 ;;
        --password)   PASSWORD="$2"; shift 2 ;;
        --container)  CONTAINER="$2"; shift 2 ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Run with --help for usage." >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAILED=()

pass() { printf '%-44s ... \033[32mOK\033[0m\n' "$1"; }
fail() {
    printf '%-44s ... \033[31mFAIL\033[0m  %s\n' "$1" "$2"
    FAILED+=("$1: $2")
}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

# [1/6] Docker container running
running=$(docker ps --filter "name=^${CONTAINER}\$" --filter 'status=running' --format '{{.Names}}' 2>/dev/null || true)
if [[ "$running" == "$CONTAINER" ]]; then
    pass "[1/6] ${CONTAINER} running"
else
    fail "[1/6] ${CONTAINER} running" "container not in 'docker ps' — run: docker start ${CONTAINER}"
fi

# [2/6] Swagger reachable
swagger_code=$(curl -sk -o /dev/null -w '%{http_code}' -m 5 "${API_BASE}/swagger/v1/swagger.json" 2>/dev/null || echo "000")
if [[ "$swagger_code" == "200" ]]; then
    pass "[2/6] swagger reachable"
else
    fail "[2/6] swagger reachable" "GET ${API_BASE}/swagger/v1/swagger.json → ${swagger_code} (API not started? run: claire fivepoints test-env-start)"
fi

# [3/6] Login → token
login_body=$(curl -sk -m 5 -X POST "${API_BASE}/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}" 2>/dev/null || echo '{}')
TOKEN=$(printf '%s' "$login_body" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('token','') or '')
except Exception:
    print('')" 2>/dev/null)
if [[ -n "$TOKEN" ]]; then
    pass "[3/6] login ${USERNAME} → token (${#TOKEN} chars)"
else
    fail "[3/6] login ${USERNAME}" "POST ${API_BASE}/auth/login returned no token (check password; if API in Production mode, RecaptchaOn=true silently rejects login — set ASPNETCORE_ENVIRONMENT=Development)"
    TOKEN=""  # avoid unbound for downstream checks
fi

# Helper for authenticated GET that returns "code|count" where count is list length
probe_list() {
    local path="$1"
    local body
    body=$(curl -sk -m 5 -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/${path}" 2>/dev/null || echo '')
    local code
    code=$(curl -sk -m 5 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/${path}" 2>/dev/null || echo "000")
    local count
    count=$(printf '%s' "$body" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    if isinstance(d, list): print(len(d))
    elif isinstance(d, dict):
        for k in ('list','items','data'):
            v=d.get(k)
            if isinstance(v, list): print(len(v)); break
        else: print(0)
    else: print(0)
except Exception:
    print(0)" 2>/dev/null || echo 0)
    printf '%s|%s\n' "$code" "$count"
}

# [4/6] Reference: StateType
if [[ -n "$TOKEN" ]]; then
    res=$(probe_list 'references/StateType')
    code="${res%|*}"; count="${res##*|}"
    if [[ "$code" == "200" && "$count" -gt 0 ]]; then
        pass "[4/6] references/StateType → list[${count}]"
    else
        fail "[4/6] references/StateType" "code=${code} count=${count} (DB seeded? migrations applied?)"
    fi
else
    fail "[4/6] references/StateType" "skipped — no token from [3/6]"
fi

# [5/6] Reference: CountyType
if [[ -n "$TOKEN" ]]; then
    res=$(probe_list 'references/CountyType')
    code="${res%|*}"; count="${res##*|}"
    if [[ "$code" == "200" && "$count" -gt 0 ]]; then
        pass "[5/6] references/CountyType → list[${count}]"
    else
        fail "[5/6] references/CountyType" "code=${code} count=${count}"
    fi
else
    fail "[5/6] references/CountyType" "skipped — no token from [3/6]"
fi

# [6/6] Users / organization (Bearer-protected, common cause of empty dropdowns)
if [[ -n "$TOKEN" ]]; then
    user_code=$(curl -sk -m 5 -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/users/organization" 2>/dev/null || echo "000")
    if [[ "$user_code" == "200" ]]; then
        pass "[6/6] users/organization    → ${user_code}"
    else
        fail "[6/6] users/organization" "code=${user_code} (token rejected? wrong scope?)"
    fi
else
    fail "[6/6] users/organization" "skipped — no token from [3/6]"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
if [[ ${#FAILED[@]} -eq 0 ]]; then
    echo "✅ All 6 checks passed."
    exit 0
else
    echo "❌ ${#FAILED[@]} check(s) failed:"
    for f in "${FAILED[@]}"; do echo "   - $f"; done
    exit 1
fi

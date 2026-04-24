#!/usr/bin/env bats
# tests/scripts/test_smoke_test.bats
#
# Tests for domain/commands/smoke-test.sh.
# Verifies the issue #118 stack-health probe:
#   - Pass when all 6 checks succeed
#   - Fail with named reason when each individual check fails
#   - Help / agent-help output present
#   - Skip downstream API checks when login fails
#
# Mocks `docker` and `curl` to return controlled responses; uses real python3 + jq.

SMOKE="${BATS_TEST_DIRNAME}/../../domain/commands/smoke-test.sh"

setup() {
    mkdir -p "$BATS_TEST_TMPDIR/bin"
    # docker mock — reads MOCK_DOCKER_RUNNING + MOCK_CONTAINER_NAME at runtime
    # so individual tests can override either.
    cat > "$BATS_TEST_TMPDIR/bin/docker" <<'SH'
#!/usr/bin/env bash
if [[ "$1" == "ps" && "$*" == *"--filter"* ]]; then
    if [[ "${MOCK_DOCKER_RUNNING:-1}" == "1" ]]; then
        echo "${MOCK_CONTAINER_NAME:-tfione-sqlserver}"
    fi
    exit 0
fi
exit 0
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/docker"

    # Default curl mock: all endpoints succeed. Defaults applied via -z guards
    # rather than ${VAR:-default} because JSON defaults contain '}' which
    # prematurely terminates bash parameter expansion.
    cat > "$BATS_TEST_TMPDIR/bin/curl" <<'SH'
#!/usr/bin/env bash
url=""
want_code=0
post_body=""
is_post=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -X) [[ "$2" == "POST" ]] && is_post=1; shift 2 ;;
        -d) post_body="$2"; shift 2 ;;
        -w) [[ "$2" == "%{http_code}" ]] && want_code=1; shift 2 ;;
        -o) shift 2 ;;
        -H) shift 2 ;;
        -m|--max-time) shift 2 ;;
        -s|-k|-sk|-ks) shift ;;
        --*) shift ;;
        http*|https*) url="$1"; shift ;;
        *) shift ;;
    esac
done

# Apply defaults (cannot inline in ${VAR:-…} because '}' would close it).
[[ -z "${MOCK_SWAGGER_CODE:-}" ]] && MOCK_SWAGGER_CODE=200
[[ -z "${MOCK_LOGIN_CODE:-}" ]]   && MOCK_LOGIN_CODE=200
[[ -z "${MOCK_LOGIN_BODY:-}" ]]   && MOCK_LOGIN_BODY='{"token":"abcdef0123456789"}'
[[ -z "${MOCK_STATE_CODE:-}" ]]   && MOCK_STATE_CODE=200
[[ -z "${MOCK_STATE_BODY:-}" ]]   && MOCK_STATE_BODY='[{"id":1},{"id":2},{"id":3}]'
[[ -z "${MOCK_COUNTY_CODE:-}" ]]  && MOCK_COUNTY_CODE=200
[[ -z "${MOCK_COUNTY_BODY:-}" ]]  && MOCK_COUNTY_BODY='[{"id":1},{"id":2}]'
[[ -z "${MOCK_USERS_CODE:-}" ]]   && MOCK_USERS_CODE=200
[[ -z "${MOCK_USERS_BODY:-}" ]]   && MOCK_USERS_BODY='[{"id":1}]'

case "$url" in
    *"/swagger/v1/swagger.json")
        [[ $want_code -eq 1 ]] && echo "$MOCK_SWAGGER_CODE"
        exit 0 ;;
    *"/auth/login")
        if [[ $want_code -eq 1 ]]; then echo "$MOCK_LOGIN_CODE"; else printf '%s' "$MOCK_LOGIN_BODY"; fi
        exit 0 ;;
    *"/references/StateType")
        if [[ $want_code -eq 1 ]]; then echo "$MOCK_STATE_CODE"; else printf '%s' "$MOCK_STATE_BODY"; fi
        exit 0 ;;
    *"/references/CountyType")
        if [[ $want_code -eq 1 ]]; then echo "$MOCK_COUNTY_CODE"; else printf '%s' "$MOCK_COUNTY_BODY"; fi
        exit 0 ;;
    *"/users/organization")
        if [[ $want_code -eq 1 ]]; then echo "$MOCK_USERS_CODE"; else printf '%s' "$MOCK_USERS_BODY"; fi
        exit 0 ;;
    *)
        [[ $want_code -eq 1 ]] && echo "404"
        exit 0 ;;
esac
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/curl"

    # Real python3
    if command -v python3 &>/dev/null; then
        ln -sf "$(command -v python3)" "$BATS_TEST_TMPDIR/bin/python3"
    fi

    export PATH="$BATS_TEST_TMPDIR/bin:$PATH"
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

# ---------------------------------------------------------------------------
# Help & arg parsing
# ---------------------------------------------------------------------------

@test "--help prints usage and exits 0" {
    run "$SMOKE" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"claire fivepoints smoke-test"* ]]
    [[ "$output" == *"Checks (in order):"* ]]
}

@test "-h prints usage" {
    run "$SMOKE" -h
    [ "$status" -eq 0 ]
    [[ "$output" == *"claire fivepoints smoke-test"* ]]
}

@test "--agent-help prints LLM-optimized help" {
    run "$SMOKE" --agent-help
    [ "$status" -eq 0 ]
    [[ "$output" == *"LLM Agent Guide"* ]]
    [[ "$output" == *"seed-test-data"* ]]
}

@test "unknown argument exits 2" {
    run "$SMOKE" --bogus
    [ "$status" -eq 2 ]
    [[ "$output" == *"Unknown argument"* ]]
}

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@test "all 6 checks pass with default mocks" {
    run "$SMOKE"
    [ "$status" -eq 0 ]
    [[ "$output" == *"[1/6] tfione-sqlserver running"* ]]
    [[ "$output" == *"[2/6] swagger reachable"* ]]
    [[ "$output" == *"[3/6] login prime.user"* ]]
    [[ "$output" == *"[4/6] references/StateType"* ]]
    [[ "$output" == *"[5/6] references/CountyType"* ]]
    [[ "$output" == *"[6/6] users/organization"* ]]
    [[ "$output" == *"All 6 checks passed"* ]]
}

# ---------------------------------------------------------------------------
# Per-check failures
# ---------------------------------------------------------------------------

@test "[1/6] fails when docker container is not running" {
    export MOCK_DOCKER_RUNNING=0
    run "$SMOKE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[1/6] tfione-sqlserver running"* ]]
    [[ "$output" == *"FAIL"* ]]
    [[ "$output" == *"docker start tfione-sqlserver"* ]]
}

@test "[2/6] fails when swagger returns non-200" {
    export MOCK_SWAGGER_CODE=000
    run "$SMOKE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[2/6] swagger reachable"* ]]
    [[ "$output" == *"FAIL"* ]]
    [[ "$output" == *"test-env-start"* ]]
}

@test "[3/6] fails when login returns no token" {
    export MOCK_LOGIN_BODY='{"token":null,"userName":null}'
    run "$SMOKE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[3/6] login prime.user"* ]]
    [[ "$output" == *"no token"* ]]
    [[ "$output" == *"RecaptchaOn"* ]]
}

@test "downstream checks [4/6][5/6][6/6] are skipped when login fails" {
    export MOCK_LOGIN_BODY='{"token":""}'
    run "$SMOKE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[4/6] references/StateType"* ]]
    [[ "$output" == *"skipped — no token"* ]]
    [[ "$output" == *"[5/6] references/CountyType"* ]]
    [[ "$output" == *"[6/6] users/organization"* ]]
}

@test "[4/6] fails when StateType returns empty list" {
    export MOCK_STATE_BODY='[]'
    run "$SMOKE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[4/6] references/StateType"* ]]
    [[ "$output" == *"FAIL"* ]]
    [[ "$output" == *"count=0"* ]]
}

@test "[5/6] fails when CountyType returns 401" {
    export MOCK_COUNTY_CODE=401
    export MOCK_COUNTY_BODY='{"error":"unauthorized"}'
    run "$SMOKE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[5/6] references/CountyType"* ]]
    [[ "$output" == *"code=401"* ]]
}

@test "[6/6] fails when users/organization returns 500" {
    export MOCK_USERS_CODE=500
    run "$SMOKE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"[6/6] users/organization"* ]]
    [[ "$output" == *"code=500"* ]]
}

@test "summary lists count of failed checks" {
    export MOCK_DOCKER_RUNNING=0
    export MOCK_SWAGGER_CODE=000
    run "$SMOKE"
    [ "$status" -eq 1 ]
    [[ "$output" == *"check(s) failed:"* ]]
    [[ "$output" == *"[1/6]"* ]]
    [[ "$output" == *"[2/6]"* ]]
}

# ---------------------------------------------------------------------------
# Custom args propagate
# ---------------------------------------------------------------------------

@test "--user override is reflected in output" {
    run "$SMOKE" --user other.user --password Secret!
    [ "$status" -eq 0 ]
    [[ "$output" == *"[3/6] login other.user"* ]]
}

@test "--container override is reflected in output" {
    export MOCK_CONTAINER_NAME=other-sql
    run "$SMOKE" --container other-sql
    [ "$status" -eq 0 ]
    [[ "$output" == *"[1/6] other-sql running"* ]]
}

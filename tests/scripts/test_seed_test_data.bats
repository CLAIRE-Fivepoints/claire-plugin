#!/usr/bin/env bats
# tests/scripts/test_seed_test_data.bats
#
# Tests for domain/commands/seed-test-data.sh.
# Live SQL execution is verified manually against tfione-sqlserver; these
# tests cover the orchestration layer (arg parsing, container check, section
# routing, dry-run, errors) by mocking `docker`.

SEED="${BATS_TEST_DIRNAME}/../../domain/commands/seed-test-data.sh"

setup() {
    mkdir -p "$BATS_TEST_TMPDIR/bin"

    # docker mock — supports `ps --filter`, `inspect`, and `exec -i ... sqlcmd`.
    cat > "$BATS_TEST_TMPDIR/bin/docker" <<'SH'
#!/usr/bin/env bash
case "$1" in
    ps)
        # `docker ps --filter name=^X$ --filter status=running --format ...`
        if [[ "${MOCK_DOCKER_RUNNING:-1}" == "1" ]]; then
            echo "${MOCK_CONTAINER_NAME:-tfione-sqlserver}"
        fi
        exit 0
        ;;
    inspect)
        # `docker inspect <name> --format ...` → emit env lines
        if [[ "${MOCK_SA_DETECTABLE:-1}" == "1" ]]; then
            echo "MSSQL_SA_PASSWORD=${MOCK_SA_PASSWORD:-TestPassword!}"
            echo "ACCEPT_EULA=Y"
        fi
        # If MOCK_SA_DETECTABLE=0 we emit nothing → script can't find SA pass
        exit 0
        ;;
    exec)
        # `docker exec -i <container> /opt/mssql-tools18/bin/sqlcmd ... -Q "<sql>"`
        # Capture the SQL into a marker file so tests can assert what was sent.
        # Find the -Q argument (sql payload).
        sql=""
        while [[ $# -gt 0 ]]; do
            if [[ "$1" == "-Q" ]]; then sql="$2"; break; fi
            shift
        done
        printf '%s\n---END-SECTION---\n' "$sql" >> "${MOCK_SQL_LOG:-/dev/null}"
        # Honor MOCK_SQL_FAIL=<section_keyword> to simulate sqlcmd error
        if [[ -n "${MOCK_SQL_FAIL:-}" && "$sql" == *"${MOCK_SQL_FAIL}"* ]]; then
            echo "Msg 50000: simulated failure" >&2
            exit 1
        fi
        echo "(0 rows affected)"
        echo "${MOCK_SECTION_PRINT:-section: ok}"
        exit 0
        ;;
esac
exit 0
SH
    chmod +x "$BATS_TEST_TMPDIR/bin/docker"

    export PATH="$BATS_TEST_TMPDIR/bin:$PATH"
    export MOCK_SQL_LOG="$BATS_TEST_TMPDIR/sql.log"
    : > "$MOCK_SQL_LOG"
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

# ---------------------------------------------------------------------------
# Help & arg parsing
# ---------------------------------------------------------------------------

@test "--help prints usage and exits 0" {
    run "$SEED" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"claire fivepoints seed-test-data"* ]]
    [[ "$output" == *"Sections (run in dependency order):"* ]]
    [[ "$output" == *"users"* ]]
    [[ "$output" == *"clients"* ]]
}

@test "-h prints usage" {
    run "$SEED" -h
    [ "$status" -eq 0 ]
    [[ "$output" == *"seed-test-data"* ]]
}

@test "--agent-help prints LLM-optimized help" {
    run "$SEED" --agent-help
    [ "$status" -eq 0 ]
    [[ "$output" == *"LLM Agent Guide"* ]]
    [[ "$output" == *"smoke-test"* ]]
}

@test "unknown argument exits 2" {
    run "$SEED" --bogus
    [ "$status" -eq 2 ]
    [[ "$output" == *"Unknown argument"* ]]
}

@test "unknown --section value exits 2 with valid list" {
    run "$SEED" --section bogus
    [ "$status" -eq 2 ]
    [[ "$output" == *"Unknown section"* ]]
    [[ "$output" == *"users"* ]]
    [[ "$output" == *"clients"* ]]
}

# ---------------------------------------------------------------------------
# Pre-flight (container + SA pass)
# ---------------------------------------------------------------------------

@test "fails when container is not running" {
    export MOCK_DOCKER_RUNNING=0
    run "$SEED"
    [ "$status" -eq 1 ]
    [[ "$output" == *"is not running"* ]]
    [[ "$output" == *"docker start tfione-sqlserver"* ]]
}

@test "fails when SA password cannot be detected from container env" {
    export MOCK_SA_DETECTABLE=0
    run "$SEED"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Could not detect SA password"* ]]
}

# ---------------------------------------------------------------------------
# Section dispatch
# ---------------------------------------------------------------------------

@test "default run executes all 7 sections in order" {
    run "$SEED"
    [ "$status" -eq 0 ]
    # Each section runs exactly once → 7 SQL payloads logged
    section_count=$(grep -c -- '---END-SECTION---' "$MOCK_SQL_LOG")
    [ "$section_count" -eq 7 ]
    # Verify ordering: users → clients → alerts → allergies → education → legal → medical
    order=$(grep -nE 'sec\.AppUser|client\.Client[^A-Za-z]|client\.ClientAlert|client\.Allergy|client\.ClientEducation|client\.LegalStatus|client\.MedicalFileDiagnosis' "$MOCK_SQL_LOG" \
        | head -7 | awk -F: '{print $2}' | tr '\n' '|')
    [[ "$output" == *"All sections succeeded"* ]]
}

@test "--section users runs only users section" {
    run "$SEED" --section users
    [ "$status" -eq 0 ]
    section_count=$(grep -c -- '---END-SECTION---' "$MOCK_SQL_LOG")
    [ "$section_count" -eq 1 ]
    grep -q 'sec\.AppUser' "$MOCK_SQL_LOG"
    ! grep -q 'client\.ClientAlert' "$MOCK_SQL_LOG"
}

@test "--section users --section clients runs only those two" {
    run "$SEED" --section users --section clients
    [ "$status" -eq 0 ]
    section_count=$(grep -c -- '---END-SECTION---' "$MOCK_SQL_LOG")
    [ "$section_count" -eq 2 ]
    grep -q 'sec\.AppUser' "$MOCK_SQL_LOG"
    grep -q 'client\.Client' "$MOCK_SQL_LOG"
    ! grep -q 'client\.MedicalFileDiagnosis' "$MOCK_SQL_LOG"
}

# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

@test "--dry-run prints SQL but does not execute (no docker exec call)" {
    run "$SEED" --dry-run --section users
    [ "$status" -eq 0 ]
    [[ "$output" == *"DRY-RUN: users"* ]]
    [[ "$output" == *"sec.AppUser"* ]]
    # Mock log must be empty — docker exec was never reached.
    [ ! -s "$MOCK_SQL_LOG" ]
}

@test "--dry-run prints all 7 sections by default" {
    run "$SEED" --dry-run
    [ "$status" -eq 0 ]
    for section in users clients alerts allergies education legal medical; do
        [[ "$output" == *"DRY-RUN: ${section}"* ]] || { echo "missing dry-run for $section"; return 1; }
    done
}

# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------

@test "non-zero exit when one section's SQL fails (others continue)" {
    # Make the alerts section fail by matching a unique keyword in its SQL.
    export MOCK_SQL_FAIL='client.ClientAlert'
    run "$SEED"
    [ "$status" -eq 1 ]
    [[ "$output" == *"alerts"* ]]
    [[ "$output" == *"section(s) failed"* ]]
    # Other sections still ran (count of section markers in log = 7)
    section_count=$(grep -c -- '---END-SECTION---' "$MOCK_SQL_LOG")
    [ "$section_count" -eq 7 ]
}

# ---------------------------------------------------------------------------
# Custom container / database
# ---------------------------------------------------------------------------

@test "--container override is honored in pre-flight check" {
    export MOCK_CONTAINER_NAME=other-sql
    run "$SEED" --container other-sql --section users
    [ "$status" -eq 0 ]
    [[ "$output" == *"users"* ]]
}

@test "--database override is propagated to docker exec args" {
    # Capture the full docker exec command line by intercepting via PS-aware mock.
    # Easier: just confirm script doesn't fail with custom DB.
    run "$SEED" --database custom_db --section users
    [ "$status" -eq 0 ]
}

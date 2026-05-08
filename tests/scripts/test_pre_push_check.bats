#!/usr/bin/env bats
# tests/scripts/test_pre_push_check.bats
#
# Tests for domain/commands/pre-push-check.sh.
# Covers Gate 0 (source control hygiene) and Gate 5b (FK reference check)
# without requiring dotnet/npm/flyway; those gates are covered by stub-based
# tests that verify the correct command is invoked.

SCRIPT="${BATS_TEST_DIRNAME}/../../domain/commands/pre-push-check.sh"

# ─────────────────────────────────────────────────────────────
# setup / teardown
# ─────────────────────────────────────────────────────────────

setup() {
    export GIT_AUTHOR_NAME="bats"
    export GIT_AUTHOR_EMAIL="bats@test.local"
    export GIT_COMMITTER_NAME="bats"
    export GIT_COMMITTER_EMAIL="bats@test.local"

    # Fake TFI One repo — minimal structure needed by the script.
    FAKE_REPO="$BATS_TEST_TMPDIR/TFIOneGit"
    git init -q --initial-branch=feature/12345-my-feature "$FAKE_REPO"
    pushd "$FAKE_REPO" >/dev/null

    touch com.tfione.sln
    mkdir -p com.tfione.db/migration
    # Gate 3/4 cd into com.tfione.web — create it so the npm stub is reachable.
    mkdir -p com.tfione.web
    echo '{"scripts":{"build-gate":"true","lint":"true"}}' > com.tfione.web/package.json
    git add com.tfione.sln com.tfione.db com.tfione.web
    git commit -q -m "seed"

    popd >/dev/null

    # Stub bin dir — override external tools so tests run without them.
    # Each stub writes to $STUB_LOG and checks its own exit-code env var.
    # Single-quoted heredocs avoid bash-4 ${VAR^^} on macOS bash 3.2.
    STUB_BIN="$BATS_TEST_TMPDIR/bin"
    mkdir -p "$STUB_BIN"
    export STUB_LOG="$BATS_TEST_TMPDIR/stub.log"
    : > "$STUB_LOG"

    cat > "$STUB_BIN/dotnet" <<'STUB'
#!/usr/bin/env bash
printf 'stub-dotnet %s\n' "$*" >> "${STUB_LOG:-/dev/null}"
exit "${STUB_DOTNET_EXIT:-0}"
STUB

    cat > "$STUB_BIN/npm" <<'STUB'
#!/usr/bin/env bash
printf 'stub-npm %s\n' "$*" >> "${STUB_LOG:-/dev/null}"
exit "${STUB_NPM_EXIT:-0}"
STUB

    cat > "$STUB_BIN/npx" <<'STUB'
#!/usr/bin/env bash
printf 'stub-npx %s\n' "$*" >> "${STUB_LOG:-/dev/null}"
exit "${STUB_NPX_EXIT:-0}"
STUB

    cat > "$STUB_BIN/claire" <<'STUB'
#!/usr/bin/env bash
printf 'stub-claire %s\n' "$*" >> "${STUB_LOG:-/dev/null}"
exit "${STUB_CLAIRE_EXIT:-0}"
STUB

    cat > "$STUB_BIN/flyway" <<'STUB'
#!/usr/bin/env bash
printf 'stub-flyway %s\n' "$*" >> "${STUB_LOG:-/dev/null}"
exit "${STUB_FLYWAY_EXIT:-0}"
STUB

    cat > "$STUB_BIN/docker" <<'STUB'
#!/usr/bin/env bash
printf 'stub-docker %s\n' "$*" >> "${STUB_LOG:-/dev/null}"
exit "${STUB_DOCKER_EXIT:-0}"
STUB

    # curl: Gate 3 API health check — return success immediately so tests
    # don't block on the 120s swagger wait loop.
    cat > "$STUB_BIN/curl" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

    # pkill: invoked by Gate 3 to kill any existing API process.
    cat > "$STUB_BIN/pkill" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

    for stub in dotnet npm npx claire flyway docker curl pkill; do
        chmod +x "$STUB_BIN/$stub"
    done

    export PATH="$STUB_BIN:$PATH"
}

teardown() {
    rm -rf "$BATS_TEST_TMPDIR"
}

# Helper: stage a file in the fake repo and optionally give it content.
stage_file() {
    local path="$1" content="${2:-placeholder}"
    pushd "$FAKE_REPO" >/dev/null
    mkdir -p "$(dirname "$path")"
    printf '%s\n' "$content" > "$path"
    git add "$path"
    popd >/dev/null
}

# Helper: run the script against the fake repo.
run_check() {
    run bash "$SCRIPT" --path "$FAKE_REPO" --skip-api "$@"
}

# ─────────────────────────────────────────────────────────────
# --help / --agent-help
# ─────────────────────────────────────────────────────────────

@test "--help exits 0 and prints usage" {
    run bash "$SCRIPT" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"claire fivepoints pre-push-check"* ]]
    [[ "$output" == *"Gate 5b"* ]]
}

@test "--agent-help exits 0 and prints FK check description" {
    run bash "$SCRIPT" --agent-help
    [ "$status" -eq 0 ]
    [[ "$output" == *"FK reference check"* ]]
}

# ─────────────────────────────────────────────────────────────
# Path validation
# ─────────────────────────────────────────────────────────────

@test "exits 1 with clear error when --path is not a TFI One repo" {
    run bash "$SCRIPT" --path "$BATS_TEST_TMPDIR/does-not-exist"
    [ "$status" -eq 1 ]
    [[ "$output" == *"com.tfione.sln not found"* ]]
}

@test "unknown argument exits 1 with usage hint" {
    run bash "$SCRIPT" --path "$FAKE_REPO" --unknown-flag
    [ "$status" -eq 1 ]
    [[ "$output" == *"Unknown argument"* ]]
}

# ─────────────────────────────────────────────────────────────
# Gate 0 — Branch naming
# ─────────────────────────────────────────────────────────────

@test "Gate 0 passes on feature/{numeric-id}-* branch" {
    # The fake repo was initialised on feature/12345-my-feature.
    # With all other gates stubbed to pass, Gate 0 should be the only real check.
    # We need something staged for the script to reach Gate 1.
    stage_file "docs/README.md" "hello"
    run_check
    # Gate 0 line should be a pass (✅), not a fail (❌)
    [[ "$output" == *"✅ Gate 0"* ]]
}

@test "Gate 0 fails on a branch not following naming convention" {
    pushd "$FAKE_REPO" >/dev/null
    git checkout -q -b "my-feature-without-ticket-id"
    popd >/dev/null

    stage_file "docs/README.md" "hello"
    run_check
    [ "$status" -eq 1 ]
    [[ "$output" == *"❌ Gate 0"* ]]
    [[ "$output" == *"naming convention"* ]]
}

@test "Gate 0 passes on bugfix/{numeric-id}-* branch" {
    pushd "$FAKE_REPO" >/dev/null
    git checkout -q -b "bugfix/9999-fix-null-ref"
    popd >/dev/null

    stage_file "docs/README.md" "hello"
    run_check
    [[ "$output" == *"✅ Gate 0"* ]]
}

@test "Gate 0 passes on main branch" {
    pushd "$FAKE_REPO" >/dev/null
    git checkout -q -b "main"
    popd >/dev/null

    stage_file "docs/README.md" "hello"
    run_check
    [[ "$output" == *"✅ Gate 0"* ]]
}

# ─────────────────────────────────────────────────────────────
# Gate 0 — com.tfione.api.d.ts check
# ─────────────────────────────────────────────────────────────

@test "Gate 0 fails when com.tfione.api.d.ts is staged" {
    stage_file "com.tfione.api.d.ts" "generated"
    run_check
    [ "$status" -eq 1 ]
    [[ "$output" == *"com.tfione.api.d.ts must not be committed"* ]]
}

# ─────────────────────────────────────────────────────────────
# Gate 0 — No test files staged
# ─────────────────────────────────────────────────────────────

@test "Gate 0 fails when a *.spec.ts file is staged" {
    stage_file "com.tfione.web/src/foo.spec.ts" "describe('foo', () => {});"
    run_check
    [ "$status" -eq 1 ]
    [[ "$output" == *"Test files staged"* ]]
}

@test "Gate 0 fails when a *.test.cs file is staged" {
    stage_file "com.tfione.service.test/client/ClientTests.test.cs" "namespace client {}"
    run_check
    [ "$status" -eq 1 ]
    [[ "$output" == *"Test files staged"* ]]
}

# ─────────────────────────────────────────────────────────────
# Gate 0 — No GRANT/DENY in staged migrations
# ─────────────────────────────────────────────────────────────

@test "Gate 0 fails when staged migration contains GRANT" {
    stage_file "com.tfione.db/migration/V1.0.20260101.1.1__foo.sql" \
        "GRANT SELECT ON dbo.Client TO app_role;"
    run_check
    [ "$status" -eq 1 ]
    [[ "$output" == *"role permissions (GRANT/DENY)"* ]]
}

@test "Gate 0 fails when staged migration contains DENY" {
    stage_file "com.tfione.db/migration/V1.0.20260101.1.1__foo.sql" \
        "DENY SELECT ON dbo.Client TO app_role;"
    run_check
    [ "$status" -eq 1 ]
    [[ "$output" == *"role permissions (GRANT/DENY)"* ]]
}

@test "Gate 0 passes for a clean migration with only DDL" {
    stage_file "com.tfione.db/migration/V1.0.20260101.1.1__create_ref_table.sql" \
        "CREATE TABLE [ref].[StatusType] ( [Id] INT NOT NULL PRIMARY KEY );"
    run_check
    [[ "$output" == *"✅ Gate 0"* ]]
}

# ─────────────────────────────────────────────────────────────
# Gate 5 — skipped when no SQL staged
# ─────────────────────────────────────────────────────────────

@test "Gate 5 is skipped when no SQL files are staged" {
    stage_file "docs/README.md" "hello"
    run_check
    [[ "$output" == *"No staged SQL files — migration gates skipped"* ]]
    # Must not have any Gate 5a/5b/5c output
    [[ "$output" != *"Gate 5a"* ]]
    [[ "$output" != *"Gate 5b"* ]]
}

# ─────────────────────────────────────────────────────────────
# Gate 5b — FK reference check
# ─────────────────────────────────────────────────────────────

@test "Gate 5b passes when FK references a table with an existing migration" {
    # Existing migration that creates the referenced table (already committed)
    pushd "$FAKE_REPO" >/dev/null
    cat > com.tfione.db/migration/V1.0.20260101.1.1__create_ref_status_type.sql <<'SQL'
CREATE TABLE [ref].[ServiceRequestStatusType] (
    [ServiceRequestStatusTypeId] INT NOT NULL CONSTRAINT [PK_ServiceRequestStatusType] PRIMARY KEY
);
SQL
    git add com.tfione.db/migration/V1.0.20260101.1.1__create_ref_status_type.sql
    git commit -q -m "existing: create ref status type"
    popd >/dev/null

    # New staged migration that adds a FK referencing the existing table
    stage_file "com.tfione.db/migration/V1.0.20260102.1.1__create_case_request.sql" \
        "$(cat <<'SQL'
CREATE TABLE [case].[CaseServiceRequest] (
    [CaseServiceRequestId] UNIQUEIDENTIFIER NOT NULL
        CONSTRAINT [PK_CaseServiceRequest] PRIMARY KEY,
    [StatusTypeId] INT NOT NULL
        CONSTRAINT [FK_CaseServiceRequest_ServiceRequestStatusType]
        FOREIGN KEY REFERENCES [ref].[ServiceRequestStatusType]([ServiceRequestStatusTypeId])
);
SQL
)"
    run_check
    [ "$status" -eq 0 ]
    [[ "$output" == *"✅ Gate 5b"* ]]
    [[ "$output" == *"all referenced tables have migrations"* ]]
}

@test "Gate 5b fails when FK references a table with no migration" {
    # Staged migration referencing a table that has NO CREATE TABLE anywhere
    stage_file "com.tfione.db/migration/V1.0.20260102.1.1__create_case_request.sql" \
        "$(cat <<'SQL'
CREATE TABLE [case].[CaseServiceRequest] (
    [CaseServiceRequestId] UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
    [StatusTypeId] INT NOT NULL
        CONSTRAINT [FK_CaseServiceRequest_ServiceRequestStatusType]
        FOREIGN KEY REFERENCES [ref].[ServiceRequestStatusType]([ServiceRequestStatusTypeId])
);
SQL
)"
    run_check
    [ "$status" -eq 1 ]
    [[ "$output" == *"❌ Gate 5b"* ]]
    [[ "$output" == *"[ref].[ServiceRequestStatusType]"* ]]
    [[ "$output" == *"no migration"* ]]
    [[ "$output" == *"Will fail on CI empty-DB"* ]]
}

@test "Gate 5b error message includes actionable fix instruction" {
    stage_file "com.tfione.db/migration/V1.0.20260102.1.1__create_case_request.sql" \
        "CONSTRAINT [FK_X] FOREIGN KEY REFERENCES [ref].[MissingTable]([Id])"
    run_check
    [ "$status" -eq 1 ]
    [[ "$output" == *"Fix:"* ]]
    [[ "$output" == *"CREATE TABLE [ref].[MissingTable]"* ]]
}

@test "Gate 5b passes when migration has no FK constraints at all" {
    stage_file "com.tfione.db/migration/V1.0.20260102.1.1__add_column.sql" \
        "ALTER TABLE [ref].[SomeTable] ADD [NewCol] NVARCHAR(100) NULL;"
    run_check
    [ "$status" -eq 0 ]
    [[ "$output" == *"✅ Gate 5b"* ]]
}

@test "Gate 5b detects FK in the same staged migration batch that creates the referenced table" {
    # Staged migration A creates the parent table
    stage_file "com.tfione.db/migration/V1.0.20260101.1.1__create_ref_type.sql" \
        "CREATE TABLE [ref].[NewRefType] ( [Id] INT NOT NULL PRIMARY KEY );"
    # Staged migration B references it — Gate 5b should find A on disk and pass
    stage_file "com.tfione.db/migration/V1.0.20260102.1.1__create_child.sql" \
        "CONSTRAINT [FK_Child_Ref] FOREIGN KEY REFERENCES [ref].[NewRefType]([Id])"
    run_check
    [ "$status" -eq 0 ]
    [[ "$output" == *"✅ Gate 5b"* ]]
}

# ─────────────────────────────────────────────────────────────
# --skip-api flag
# ─────────────────────────────────────────────────────────────

@test "--skip-api shows gate skip message for API startup" {
    stage_file "docs/README.md" "hello"
    run bash "$SCRIPT" --path "$FAKE_REPO" --skip-api
    [[ "$output" == *"API startup + type regen skipped"* ]]
}

@test "without --skip-api Gate 3 attempts to start the API (dotnet run)" {
    stage_file "docs/README.md" "hello"
    # Use a fast-failing dotnet stub for run to keep the test snappy.
    # The script will see "dotnet run" fail, which is Gate 3 — but we can't
    # easily get past the API wait loop without real curl. So just test that
    # dotnet run is invoked at all by checking the stub log.
    # We pass --skip-api=false explicitly (default) via just not passing --skip-api.
    # However the curl stub returns 0 immediately, so swagger is "ready".
    # Then dotnet run will never actually start an API — but the stub exits 0,
    # so Gate 3 proceeds. We check the stub log shows "dotnet run".
    run bash "$SCRIPT" --path "$FAKE_REPO"
    grep -q "stub-dotnet run" "$BATS_TEST_TMPDIR/stub.log"
}

# ─────────────────────────────────────────────────────────────
# Full flow with all stubs passing
# ─────────────────────────────────────────────────────────────

@test "all gates pass when everything is clean and stubs succeed" {
    stage_file "docs/README.md" "hello"
    # npm stub must succeed for both build-gate and lint
    run_check
    [ "$status" -eq 0 ]
    [[ "$output" == *"All gates passed"* ]]
    [[ "$output" == *"✅ Gate 0"* ]]
    [[ "$output" == *"✅ Gate 1"* ]]
    [[ "$output" == *"✅ Gate 2"* ]]
    [[ "$output" == *"✅ Gate 4"* ]]
}

@test "Gate 1 failure stops the run before Gate 2" {
    stage_file "docs/README.md" "hello"
    export STUB_DOTNET_EXIT=1
    run_check
    [ "$status" -eq 1 ]
    [[ "$output" == *"❌ Gate 1"* ]]
    # Gate 2 must not have run (no ✅ Gate 2)
    [[ "$output" != *"✅ Gate 2"* ]]
}
